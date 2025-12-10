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

export default {
  'Game State Log': {
    emoji: '📊',
    timestampPrompt: `Analyze the video to identify the specific round start and end times.
    - Start Time: Immediately after the "FIGHT" announcement when control is given to players, or when the health bars are fully visible and 100%.
    - End Time: When "KO" appears or the round ends.
    - Coordinates: Identify the rectangular pixel coordinates (x1,y1,x2,y2) of the inner part of the Player 1 (Left) and Player 2 (Right) health bars. Exclude the character portraits. Assume the video is 1920x1080.
    
    Note: At the start of the round (100%), the health bar is often GOLD colored. As damage is taken, it reveals a red (pending) or black (empty) background.
    Call get_round_timestamps with these values.`,
    prompt: 'This mode is now handled by Client-Side CV Analysis.',
  },

  'AI YouTuber': {
    emoji: '🎮',
    timestampPrompt: `Analyze the video to identify the specific round start and end times.
    - Start Time: Immediately after the "FIGHT" announcement when control is given to players, or when the health bars are fully visible and 100%.
    - End Time: When "KO" appears or the round ends.
    - Coordinates: Identify the rectangular pixel coordinates (x1,y1,x2,y2) of the inner part of the Player 1 (Left) and Player 2 (Right) health bars. Exclude the character portraits. Assume the video is 1920x1080.

    Note: At the start of the round (100%), the health bar is often GOLD colored. As damage is taken, it reveals a red (pending) or black (empty) background.
    Call get_round_timestamps with these values.`,
    prompt: (gameStateLog: string, scriptContent?: string) => {
      let promptText = `あなたはストリートファイターを実況プレイする「AI VTuber（女性）」です。
現在、あなたは**プレイヤー1（画面左側、体力バー左）**として操作しています。
対戦相手はプレイヤー2（画面右側、体力バー右）です。

以下に、画像解析(CV)で取得した**絶対的な正解ログ**があります。
このログの \`event_type\` に従って、プレイヤー1としてのリアクションを生成してください。

【Game State Log (CV Measurement)】
${gameStateLog}`;

      if (scriptContent) {
        promptText += `\n\n【シナリオ台本 (Script Guide)】
以下は事前に用意された演出用台本です。この台本に記述された「感情の流れ」や「セリフのニュアンス」を可能な限り再現してください。
重要: イベントの正確な発生タイミングは上記のCVログが正です。台本のタイミングとずれている場合は、CVログのタイミングに合わせて、台本の内容（感情・セリフ）を適用してください。

${scriptContent}`;
      }

      promptText += `\n\n【実況ルール：イベント別対応】

1. **damage_given** (あなたが攻撃を当てた)
   - **リアクション**: 喜び、興奮、ドヤ顔。「食らえっ！」「よしっ！」「どうだ！」
   - **大ダメージ(10%以上)**: 必殺技が決まった可能性が高い。「これで決める！」「ドカーンといけー！」
   - **映像確認**: その瞬間にどんな技（波動拳、キックなど）を出したか映像を見て、技名を叫んでも良い。

2. **damage_taken** (あなたが攻撃を食らった)
   - **リアクション**: 痛み、焦り、言い訳。「痛っ！」「うそでしょ！？」「あーもう、ラグいって！」
   - **大ダメージ**: コンボを食らっている。「やばいやばい！」「タンマ！タンマ！」

3. **neutral** (変化なし/開始)
   - **リアクション**: 様子見や意気込み。「さあ、いくよ！」「隙がないね…」

4. **victory** (あなたが勝った)
   - **リアクション**: 大喜び。「見た！？私の実力！」「GG！」

5. **defeat** (あなたが負けた)
   - **リアクション**: 悔しがる。「なんでー！？」「今の当たってないって！」

【出力形式】
set_game_commentary関数を使用してください。
- \`reasoning\`: 「CVログ: damage_given なので攻撃セリフ (台本参照)」のように記述。
- \`speech\`: 上記ルールと台本に従ったセリフ。`;
      
      return promptText;
    },
  },

  'Scene Description': {
    emoji: '👁️',
    prompt: (eventsCSV: string, p1Char?: string, p2Char?: string) => `あなたは格闘ゲームの映像解析の専門家です。
提供された「イベントタイムライン(events_timeline.csv)」の各イベントについて、映像を確認し、何が起きたかを記述してください。

【キャラクター情報】
- P1（画面左側）: ${p1Char || '不明'}
- P2（画面右側）: ${p2Char || '不明'}

【イベントタイムライン】
${eventsCSV}

【タスク】
各イベント(timestamp_ms)の時間にジャンプし、映像を確認して以下を記述してください：

1. **使用された技**:
   - 通常技: 立ち弱P、しゃがみ中K、ジャンプ強K など
   - 必殺技: 波動拳、昇龍拳、スピニングバードキック など
   - コンボ: 複数の技が繋がった場合は流れを記述
   - 投げ、ドライブインパクト、SA(スーパーアーツ)なども識別

2. **状況**:
   - 地上戦、空中戦、起き攻め、画面端 など
   - どちらが攻めていたか、守っていたか

3. **特記事項**:
   - カウンターヒット、パニッシュカウンター
   - コンボが途中で落ちた、ガードされた など

【出力形式】
set_scene_descriptions関数を使用してください。各イベントに対して：
- timestamp_ms: イベントのタイムスタンプ
- description: 上記の観点で記述した内容（日本語、簡潔に）

例:
- "立ち中Kからキャンセル波動拳がヒット"
- "ジャンプ強Kから地上コンボ、昇龍拳で締め"
- "ドライブインパクトがカウンター、壁やられからコンボ"
- "投げ抜け失敗、通常投げを食らう"
`,
  },

  'Scripted Commentary': {
    emoji: '🎬',
    prompt: (scriptContent: string) => `
    あなたは動画編集のプロフェッショナルであり、演出家です。
    提供された「実況台本(Script)」をもとに、実際のゲームプレイ動画に合わせて完璧な実況トラックを作成してください。

    【タスク】
    1. 以下の台本を読み込んでください。
    2. 動画を見て、台本にあるイベント（ダメージ発生、コンボ、KOなど）が**実際に起きている正確な時間**を特定してください。
    3. 台本に書かれたセリフ（実況ヒント）を、映像のタイミングに合わせて出力してください。
    4. 映像を見て、台本にはないが明らかな視覚的詳細（技の名前、キャラクターの位置関係など）があれば、それを加味してセリフを微調整し、より自然にしてください。

    【台本データ】
    ${scriptContent}

    【出力ルール】
    set_game_commentary関数を使用してください。
    - time: 動画内の実際の発生時刻 (例: 00:12)
    - reasoning: 「台本0:11.6のイベントを00:12で確認」のように記述。
    - speech: 台本の「実況ヒント」にあるセリフ。感情を込めて。
    - emotion: 台本の[感情タグ]を使用。
    - my_health / enemy_health: その瞬間の映像から推定した体力%。
    - situation: 台本の「状況」カラムの内容。
    `,
  },

  Chart: {
    emoji: '📈',
    prompt: (input: string) =>
      `Generate chart data for this video based on the following instructions: \
${input}. Call set_timecodes_with_numeric_values once with the list of data values and timecodes.`,
    subModes: {
      Excitement:
        'for each scene, estimate the level of excitement on a scale of 1 to 10',
      Importance:
        'for each scene, estimate the level of overall importance to the video on a scale of 1 to 10',
      'Number of people': 'for each scene, count the number of people visible',
    },
  },

  Custom: {
    emoji: '🔧',
    prompt: (input: string) =>
      `Call set_timecodes once using the following instructions: ${input}`,
    isList: true,
  },
};