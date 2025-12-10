/**
 * @license
 * SPDX-License-Identifier: Apache-2.0
*/
/* tslint:disable */
// Copyright 2024 Google LLC

// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at

//     https://www.apache.org/licenses/LICENSE-2.0

// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import c from 'classnames';
import {useRef, useState} from 'react';
import {generateContent, uploadFile} from './api';
import Chart from './Chart.jsx';
import {processHealthCSV, processVideoForHealth} from './cv';
import functions from './functions';
import modes from './modes';
import {timeToSecs} from './utils';
import VideoPlayer from './VideoPlayer.jsx';

const chartModes = Object.keys(modes.Chart.subModes);

export default function App() {
  const [vidUrl, setVidUrl] = useState(null);
  const [file, setFile] = useState(null);
  const [timecodeList, setTimecodeList] = useState(null);
  const [requestedTimecode, setRequestedTimecode] = useState(null);
  const [selectedMode, setSelectedMode] = useState(Object.keys(modes)[0]);
  const [activeMode, setActiveMode] = useState<string>();
  const [isLoading, setIsLoading] = useState(false);
  const [loadingText, setLoadingText] = useState('');
  const [cvProgress, setCvProgress] = useState(0); // Progress for CV
  const [showSidebar, setShowSidebar] = useState(true);
  const [isLoadingVideo, setIsLoadingVideo] = useState(false);
  const [videoError, setVideoError] = useState(false);
  const [customPrompt, setCustomPrompt] = useState('');
  const [chartMode, setChartMode] = useState(chartModes[0]);
  const [chartPrompt, setChartPrompt] = useState('');
  const [chartLabel, setChartLabel] = useState('');
  const [csvContent, setCsvContent] = useState<string | null>(null);
  const [scriptContent, setScriptContent] = useState<string | null>(null);
  const [p1Character, setP1Character] = useState<string>('');
  const [p2Character, setP2Character] = useState<string>('');
  const [theme] = useState(
    window.matchMedia('(prefers-color-scheme: dark)').matches
      ? 'dark'
      : 'light',
  );
  const scrollRef = useRef<HTMLElement>(null);
  const isCustomMode = selectedMode === 'Custom';
  const isChartMode = selectedMode === 'Chart';
  const isCustomChartMode = isChartMode && chartMode === 'Custom';
  const hasSubMode = isCustomMode || isChartMode;

  const setTimecodes = ({timecodes}) =>
    setTimecodeList(
      timecodes.map((t) => ({...t, text: t.text.replaceAll("\\'", "'")})),
    );

  const onCsvUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    setCsvContent(text);
  };

  const onScriptUpload = async (e) => {
    const file = e.target.files[0];
    if (!file) return;
    const text = await file.text();
    setScriptContent(text);
  };

  const downloadResults = () => {
    if (!timecodeList) return;

    // CSVヘッダー
    const headers = ['timestamp_ms', 'time', 'description'];
    const csvRows = [headers.join(',')];

    // データ行
    for (const item of timecodeList) {
      const row = [
        item.timestamp_ms || '',
        item.time || '',
        `"${(item.description || item.text || '').replace(/"/g, '""')}"`
      ];
      csvRows.push(row.join(','));
    }

    const csvContent = csvRows.join('\n');
    const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = 'phase3_output.csv';
    link.click();
    URL.revokeObjectURL(url);
  };

  const onModeSelect = async (mode) => {
    setActiveMode(mode);
    setIsLoading(true);
    setLoadingText('Initializing...');
    setCvProgress(0);
    setChartLabel(chartPrompt);
    setTimecodeList(null); // Clear previous results

    const modeConfig = modes[mode];
    let promptToUse = modeConfig.prompt;

    // --- PHASE 2: CV / Game State Analysis (if applicable) ---
    if (mode === 'AI YouTuber' || mode === 'Game State Log') {
      let events = [];

      // OPTION A: Use Uploaded CSV (Highest Accuracy)
      if (mode === 'AI YouTuber' && csvContent) {
        setLoadingText('Parsing Uploaded CSV...');
        console.log('Using uploaded CSV for Health Data...');
        try {
          events = processHealthCSV(csvContent);
        } catch (e) {
          console.error('CSV Parsing Error:', e);
          alert('Failed to parse CSV. Check the format.');
          setIsLoading(false);
          return;
        }
      } 
      // OPTION B: Run Client-Side CV
      else {
        // --- PHASE 1: Timestamp & Coordinate Detection ---
        let startTimeSecs = 0;
        let endTimeSecs = 0;
        let p1Coords = null;
        let p2Coords = null;
        
        if (modeConfig.timestampPrompt) {
          setLoadingText('Detecting Match Start/End & Coords...');
          console.log('Phase 1: Detecting Timestamps & Coords...');
          try {
            const resp = await generateContent(
              modeConfig.timestampPrompt,
              functions({
                get_round_timestamps: () => {}, // Handled by extracting call.args
              }),
              file
            );
            const call = resp.functionCalls?.[0];
            if (call && call.name === 'get_round_timestamps') {
              startTimeSecs = timeToSecs(call.args.startTime);
              endTimeSecs = timeToSecs(call.args.endTime);
              p1Coords = call.args.p1_bar_coords;
              p2Coords = call.args.p2_bar_coords;
              console.log(`Phase 1 Result: Start=${startTimeSecs}s, End=${endTimeSecs}s`);
              console.log('P1 Coords:', p1Coords);
              console.log('P2 Coords:', p2Coords);
            } else {
              console.warn('Could not detect timestamps, falling back to full video.');
            }
          } catch (e) {
            console.error('Timestamp detection failed', e);
          }
        }

        setLoadingText('Analyzing Health Bars (CV)...');
        console.log('Phase 2: Starting Client-Side CV Analysis...');
        
        try {
          events = await processVideoForHealth(
            vidUrl, 
            (pct) => {
              setCvProgress(pct);
            },
            startTimeSecs,
            endTimeSecs,
            p1Coords,
            p2Coords
          );
        } catch (err) {
          console.error('CV Error:', err);
          alert('Could not process video for health bars. Ensure the video format is supported.');
          setIsLoading(false);
          return;
        }
      }
      
      // If mode is just logging, return the table here
      if (mode === 'Game State Log') {
          setTimecodeList(events);
          setIsLoading(false);
          return;
      }

      // Prepare log for Phase 3 (Commentary)
      const logString = events.map(e => 
        `Time:${e.time}, Event:${e.event_type}, P1:${e.my_health}%, P2:${e.enemy_health}%, Note:${e.description}`
      ).join('\n');
      
      console.log('Game State Log:', logString);
      
      if (typeof modeConfig.prompt === 'function') {
          promptToUse = modeConfig.prompt(logString, scriptContent);
      }
    } else if (mode === 'Scripted Commentary') {
        // --- SCRIPT ONLY MODE ---
        if (!scriptContent) {
          alert('Please upload a script file for this mode.');
          setIsLoading(false);
          return;
        }
        if (typeof modeConfig.prompt === 'function') {
          promptToUse = modeConfig.prompt(scriptContent);
        }
    } else if (mode === 'Scene Description') {
        // --- SCENE DESCRIPTION MODE ---
        if (!csvContent) {
          alert('Please upload events_timeline.csv for this mode.');
          setIsLoading(false);
          return;
        }
        if (typeof modeConfig.prompt === 'function') {
          promptToUse = modeConfig.prompt(csvContent, p1Character, p2Character);
        }
    } else {
      // Standard logic for other modes
      if (isCustomMode) {
        promptToUse = modes[mode].prompt(customPrompt);
      } else if (isChartMode) {
        promptToUse = modes[mode].prompt(
          isCustomChartMode ? chartPrompt : modes[mode].subModes[chartMode],
        );
      } else {
        promptToUse = modes[mode].prompt;
      }
    }

    // --- PHASE 3: Generation (or Single Phase) ---
    setLoadingText('Generating Commentary...');
    console.log('Phase 3: Starting Generation...');
    
    const resp = await generateContent(
      promptToUse,
      functions({
        set_timecodes: setTimecodes,
        set_timecodes_with_objects: setTimecodes,
        set_timecodes_with_numeric_values: ({timecodes}) =>
          setTimecodeList(timecodes),
        set_game_commentary: ({rows}) =>
          setTimecodeList(rows.map((r) => ({...r, text: r.speech}))),
        analyze_game_state: ({events}) =>
          setTimecodeList(events.map((e) => ({...e, text: e.event_type}))),
        set_scene_descriptions: ({scenes}) =>
          setTimecodeList(scenes.map((s) => ({...s, text: s.description, time: `${Math.floor(s.timestamp_ms / 1000)}.${Math.floor((s.timestamp_ms % 1000) / 100)}`}))),
      }),
      file,
    );

    const call = resp.functionCalls?.[0];

    if (call) {
      ({
        set_timecodes: setTimecodes,
        set_timecodes_with_objects: setTimecodes,
        set_timecodes_with_numeric_values: ({timecodes}) =>
          setTimecodeList(timecodes),
        set_game_commentary: ({rows}) =>
          setTimecodeList(rows.map((r) => ({...r, text: r.speech}))),
        analyze_game_state: ({events}) =>
          setTimecodeList(events.map((e) => ({...e, text: e.event_type}))),
        set_scene_descriptions: ({scenes}) =>
          setTimecodeList(scenes.map((s) => ({...s, text: s.description, time: `${Math.floor(s.timestamp_ms / 1000)}.${Math.floor((s.timestamp_ms % 1000) / 100)}`}))),
      })[call.name](call.args);
    }

    setIsLoading(false);
    if (scrollRef.current) {
      scrollRef.current.scrollTo({top: 0});
    }
  };

  const uploadVideo = async (e) => {
    e.preventDefault();
    setIsLoadingVideo(true);
    setVidUrl(URL.createObjectURL(e.dataTransfer.files[0]));

    const file = e.dataTransfer.files[0];

    try {
      const res = await uploadFile(file);
      setFile(res);
      setIsLoadingVideo(false);
    } catch (e) {
      setVideoError(true);
    }
  };

  return (
    <main
      className={theme}
      onDrop={uploadVideo}
      onDragOver={(e) => e.preventDefault()}
      onDragEnter={() => {}}
      onDragLeave={() => {}}>
      <section className="top">
        {vidUrl && !isLoadingVideo && (
          <>
            <div className={c('modeSelector', {hide: !showSidebar})}>
              {hasSubMode ? (
                <>
                  <div>
                    {isCustomMode ? (
                      <>
                        <h2>Custom prompt:</h2>
                        <textarea
                          placeholder="Type a custom prompt..."
                          value={customPrompt}
                          onChange={(e) => setCustomPrompt(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              onModeSelect(selectedMode);
                            }
                          }}
                          rows={5}
                        />
                      </>
                    ) : (
                      <>
                        <h2>Chart this video by:</h2>

                        <div className="modeList">
                          {chartModes.map((mode) => (
                            <button
                              key={mode}
                              className={c('button', {
                                active: mode === chartMode,
                              })}
                              onClick={() => setChartMode(mode)}>
                              {mode}
                            </button>
                          ))}
                        </div>
                        <textarea
                          className={c({active: isCustomChartMode})}
                          placeholder="Or type a custom prompt..."
                          value={chartPrompt}
                          onChange={(e) => setChartPrompt(e.target.value)}
                          onKeyDown={(e) => {
                            if (e.key === 'Enter') {
                              e.preventDefault();
                              onModeSelect(selectedMode);
                            }
                          }}
                          onFocus={() => setChartMode('Custom')}
                          rows={2}
                        />
                      </>
                    )}
                    <button
                      className="button generateButton"
                      onClick={() => onModeSelect(selectedMode)}
                      disabled={
                        (isCustomMode && !customPrompt.trim()) ||
                        (isChartMode &&
                          isCustomChartMode &&
                          !chartPrompt.trim())
                      }>
                      ▶️ Generate
                    </button>
                  </div>
                  <div className="backButton">
                    <button
                      onClick={() => setSelectedMode(Object.keys(modes)[0])}>
                      <span className="icon">chevron_left</span>
                      Back
                    </button>
                  </div>
                </>
              ) : (
                <>
                  <div>
                    <h2>Explore this video via:</h2>
                    <div className="modeList">
                      {Object.entries(modes).map(([mode, {emoji}]: [string, any]) => (
                        <div key={mode}>
                           <button
                            className={c('button', {
                              active: mode === selectedMode,
                            })}
                            onClick={() => setSelectedMode(mode)}>
                            <span className="emoji">{emoji}</span> {mode}
                          </button>
                          
                          {/* AI YouTuber Inputs */}
                          {mode === 'AI YouTuber' && selectedMode === 'AI YouTuber' && (
                             <div style={{marginTop: '10px', fontSize:'12px', paddingLeft: '10px', borderLeft: '2px solid var(--border)'}}>
                               <div style={{marginBottom: '10px'}}>
                                  <label style={{display:'block', marginBottom:'4px', color:'var(--mid)', fontWeight: 'bold'}}>
                                    1. Health Data (CSV)
                                  </label>
                                  <input 
                                    type="file" 
                                    accept=".csv"
                                    onChange={onCsvUpload}
                                    style={{fontSize: '11px', width: '100%'}}
                                  />
                                  {csvContent && <span style={{color: 'green', display: 'block', marginTop:'2px'}}>CSV Loaded ✓</span>}
                               </div>
                             </div>
                          )}

                          {/* Scene Description Inputs */}
                          {mode === 'Scene Description' && selectedMode === 'Scene Description' && (
                             <div style={{marginTop: '10px', fontSize:'12px', paddingLeft: '10px', borderLeft: '2px solid var(--border)'}}>
                               <div style={{marginBottom: '10px'}}>
                                  <label style={{display:'block', marginBottom:'4px', color:'var(--mid)', fontWeight: 'bold'}}>
                                    Upload events_timeline.csv
                                  </label>
                                  <input
                                    type="file"
                                    accept=".csv"
                                    onChange={onCsvUpload}
                                    style={{fontSize: '11px', width: '100%'}}
                                  />
                                  {csvContent && <span style={{color: 'green', display: 'block', marginTop:'2px'}}>CSV Loaded ✓</span>}
                               </div>
                               <div style={{marginBottom: '8px'}}>
                                  <label style={{display:'block', marginBottom:'4px', color:'var(--mid)', fontWeight: 'bold'}}>
                                    P1 Character (自分)
                                  </label>
                                  <input
                                    type="text"
                                    value={p1Character}
                                    onChange={(e) => setP1Character(e.target.value)}
                                    placeholder="例: Ryu, Ken, Chun-Li..."
                                    style={{fontSize: '11px', width: '100%', padding: '4px'}}
                                  />
                               </div>
                               <div>
                                  <label style={{display:'block', marginBottom:'4px', color:'var(--mid)', fontWeight: 'bold'}}>
                                    P2 Character (相手)
                                  </label>
                                  <input
                                    type="text"
                                    value={p2Character}
                                    onChange={(e) => setP2Character(e.target.value)}
                                    placeholder="例: Ryu, Ken, Chun-Li..."
                                    style={{fontSize: '11px', width: '100%', padding: '4px'}}
                                  />
                               </div>
                               {timecodeList && (
                                 <div style={{marginTop: '10px'}}>
                                   <button
                                     onClick={downloadResults}
                                     style={{
                                       padding: '6px 12px',
                                       fontSize: '11px',
                                       cursor: 'pointer',
                                       backgroundColor: '#4CAF50',
                                       color: 'white',
                                       border: 'none',
                                       borderRadius: '4px',
                                       width: '100%'
                                     }}>
                                     📥 Download CSV
                                   </button>
                                 </div>
                               )}
                             </div>
                          )}

                          {/* Scripted Commentary Inputs */}
                          {mode === 'Scripted Commentary' && selectedMode === 'Scripted Commentary' && (
                             <div style={{marginTop: '10px', fontSize:'12px', paddingLeft: '10px', borderLeft: '2px solid var(--border)'}}>
                               <div>
                                  <label style={{display:'block', marginBottom:'4px', color:'var(--mid)', fontWeight: 'bold'}}>
                                    Upload Script (.txt/.md)
                                  </label>
                                  <input
                                    type="file"
                                    accept=".md,.txt"
                                    onChange={onScriptUpload}
                                    style={{fontSize: '11px', width: '100%'}}
                                  />
                                  {scriptContent && <span style={{color: 'green', display: 'block', marginTop:'2px'}}>Script Loaded ✓</span>}
                               </div>
                             </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                  <div>
                    <button
                      className="button generateButton"
                      onClick={() => onModeSelect(selectedMode)}>
                      ▶️ Generate
                    </button>
                  </div>
                </>
              )}
            </div>
            <button
              className="collapseButton"
              onClick={() => setShowSidebar(!showSidebar)}>
              <span className="icon">
                {showSidebar ? 'chevron_left' : 'chevron_right'}
              </span>
            </button>
          </>
        )}

        <VideoPlayer
          url={vidUrl}
          requestedTimecode={requestedTimecode}
          timecodeList={timecodeList}
          jumpToTimecode={setRequestedTimecode}
          isLoadingVideo={isLoadingVideo}
          videoError={videoError}
        />
      </section>

      <div className={c('tools', {inactive: !vidUrl})}>
        <section
          className={c('output', {['mode' + activeMode]: activeMode})}
          ref={scrollRef}>
          {isLoading ? (
            <div className="loading">
              {loadingText}
              {cvProgress > 0 && cvProgress < 100 && (
                <span> {cvProgress}%</span>
              )}
              {cvProgress === 0 && <span>...</span>}
            </div>
          ) : timecodeList ? (
            <>
              {/* Download Button */}
              <div style={{marginBottom: '10px', textAlign: 'right'}}>
                <button
                  onClick={downloadResults}
                  style={{
                    padding: '6px 12px',
                    fontSize: '12px',
                    cursor: 'pointer',
                    backgroundColor: 'var(--accent)',
                    color: 'white',
                    border: 'none',
                    borderRadius: '4px'
                  }}>
                  📥 Download CSV
                </button>
              </div>
              {activeMode === 'Table' ? (
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Description</th>
                    <th>Objects</th>
                  </tr>
                </thead>
                <tbody>
                  {timecodeList.map(({time, text, objects}, i) => (
                    <tr
                      key={i}
                      role="button"
                      onClick={() => setRequestedTimecode(timeToSecs(time))}>
                      <td>
                        <time>{time}</time>
                      </td>
                      <td>{text}</td>
                      <td>{objects.join(', ')}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (activeMode === 'AI YouTuber' || activeMode === 'Scripted Commentary') ? (
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Reasoning</th>
                    <th>Health(Me)</th>
                    <th>Health(En)</th>
                    <th>Speech</th>
                    <th>Emotion</th>
                    <th>Situation</th>
                  </tr>
                </thead>
                <tbody>
                  {timecodeList.map(
                    (
                      {
                        time,
                        reasoning,
                        my_health,
                        enemy_health,
                        speech,
                        emotion,
                        situation,
                      },
                      i,
                    ) => (
                      <tr
                        key={i}
                        role="button"
                        onClick={() => setRequestedTimecode(timeToSecs(time))}>
                        <td>
                          <time>{time}</time>
                        </td>
                        <td style={{fontSize: '0.8em', color: '#888'}}>
                          {reasoning}
                        </td>
                        <td>{my_health}%</td>
                        <td>{enemy_health}%</td>
                        <td>{speech}</td>
                        <td>{emotion}</td>
                        <td>{situation}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            ) : activeMode === 'Game State Log' ? (
              <table>
                <thead>
                  <tr>
                    <th>Time</th>
                    <th>Event Type</th>
                    <th>P1 HP (Left)</th>
                    <th>P2 HP (Right)</th>
                    <th>Description</th>
                  </tr>
                </thead>
                <tbody>
                  {timecodeList.map(
                    ({time, event_type, my_health, enemy_health, description}, i) => (
                      <tr
                        key={i}
                        role="button"
                        onClick={() => setRequestedTimecode(timeToSecs(time))}>
                        <td>
                          <time>{time}</time>
                        </td>
                        <td style={{fontWeight: 'bold'}}>
                          {event_type === 'damage_taken' ? (
                            <span style={{color: 'red'}}>Damage Taken</span>
                          ) : event_type === 'damage_given' ? (
                            <span style={{color: 'green'}}>Damage Given</span>
                          ) : (
                            event_type
                          )}
                        </td>
                        <td>{my_health}%</td>
                        <td>{enemy_health}%</td>
                        <td>{description}</td>
                      </tr>
                    ),
                  )}
                </tbody>
              </table>
            ) : activeMode === 'Chart' ? (
              <Chart
                data={timecodeList}
                yLabel={chartLabel}
                jumpToTimecode={setRequestedTimecode}
              />
            ) : activeMode && modes[activeMode].isList ? (
              <ul>
                {timecodeList.map(({time, text}, i) => (
                  <li key={i} className="outputItem">
                    <button
                      onClick={() => setRequestedTimecode(timeToSecs(time))}>
                      <time>{time}</time>
                      <p className="text">{text}</p>
                    </button>
                  </li>
                ))}
              </ul>
            ) : (
              timecodeList.map(({time, text}, i) => (
                <>
                  <span
                    key={i}
                    className="sentence"
                    role="button"
                    onClick={() => setRequestedTimecode(timeToSecs(time))}>
                    <time>{time}</time>
                    <span>{text}</span>
                  </span>{' '}
                </>
              ))
            )}
            </>
          ) : null}
        </section>
      </div>
    </main>
  );
}