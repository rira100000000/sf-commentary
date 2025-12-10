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
import {FunctionDeclaration, Type} from '@google/genai';

const functions: FunctionDeclaration[] = [
  {
    name: 'set_timecodes',
    description: 'Set the timecodes for the video with associated text',
    parameters: {
      type: Type.OBJECT,
      properties: {
        timecodes: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              time: {
                type: Type.STRING,
              },
              text: {
                type: Type.STRING,
              },
            },
            required: ['time', 'text'],
          },
        },
      },
      required: ['timecodes'],
    },
  },
  {
    name: 'set_timecodes_with_objects',
    description:
      'Set the timecodes for the video with associated text and object list',
    parameters: {
      type: Type.OBJECT,
      properties: {
        timecodes: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              time: {
                type: Type.STRING,
              },
              text: {
                type: Type.STRING,
              },
              objects: {
                type: Type.ARRAY,
                items: {
                  type: Type.STRING,
                },
              },
            },
            required: ['time', 'text', 'objects'],
          },
        },
      },
      required: ['timecodes'],
    },
  },
  {
    name: 'set_timecodes_with_numeric_values',
    description:
      'Set the timecodes for the video with associated numeric values',
    parameters: {
      type: Type.OBJECT,
      properties: {
        timecodes: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              time: {
                type: Type.STRING,
              },
              value: {
                type: Type.NUMBER,
              },
            },
            required: ['time', 'value'],
          },
        },
      },
      required: ['timecodes'],
    },
  },
  {
    name: 'get_round_timestamps',
    description: 'Get the start and end timestamps of the fighting game round and the coordinates of the health bars.',
    parameters: {
      type: Type.OBJECT,
      properties: {
        startTime: {
          type: Type.STRING,
          description: 'The timecode when the round actually begins (e.g. "00:05"). Look for the "FIGHT" announcement or when health bars first appear fully.',
        },
        endTime: {
          type: Type.STRING,
          description: 'The timecode when the round ends (e.g. KO or Time Over).',
        },
        p1_bar_coords: {
          type: Type.OBJECT,
          description: 'Coordinates for Player 1 (Left) Health Bar. Exclude the portrait. Assume 1920x1080 resolution.',
          properties: { 
            y1: {type:Type.INTEGER}, 
            y2: {type:Type.INTEGER}, 
            x1: {type:Type.INTEGER}, 
            x2: {type:Type.INTEGER} 
          },
          required: ['x1','y1','x2','y2']
        },
        p2_bar_coords: {
          type: Type.OBJECT,
          description: 'Coordinates for Player 2 (Right) Health Bar. Exclude the portrait. Assume 1920x1080 resolution.',
          properties: { 
            y1: {type:Type.INTEGER}, 
            y2: {type:Type.INTEGER}, 
            x1: {type:Type.INTEGER}, 
            x2: {type:Type.INTEGER} 
          },
          required: ['x1','y1','x2','y2']
        }
      },
      required: ['startTime', 'endTime', 'p1_bar_coords', 'p2_bar_coords'],
    },
  },
  {
    name: 'analyze_game_state',
    description:
      'Phase 1: Analyze the game state strictly based on UI/Health bars.',
    parameters: {
      type: Type.OBJECT,
      properties: {
        events: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              time: {type: Type.STRING},
              my_health: {
                type: Type.INTEGER,
                description: 'Left Health Bar % (0-100)',
              },
              enemy_health: {
                type: Type.INTEGER,
                description: 'Right Health Bar % (0-100)',
              },
              event_type: {
                type: Type.STRING,
                enum: [
                  'damage_taken',
                  'damage_given',
                  'neutral',
                  'victory',
                  'defeat',
                ],
                description:
                  'The specific event that occurred based on health bar changes.',
              },
              description: {
                type: Type.STRING,
                description: 'Brief visual description of what caused the change',
              },
            },
            required: ['time', 'my_health', 'enemy_health', 'event_type'],
          },
        },
      },
      required: ['events'],
    },
  },
  {
    name: 'set_game_commentary',
    description:
      'Phase 2: Set detailed game commentary using the provided game state log.',
    parameters: {
      type: Type.OBJECT,
      properties: {
        rows: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              time: {type: Type.STRING},
              reasoning: {
                type: Type.STRING,
                description:
                  'Reference the game state log. E.g. "Log says damage_taken at 00:05"',
              },
              my_health: {
                type: Type.INTEGER,
                description: 'Estimated % of Left Health Bar (Player 1/Me)',
              },
              enemy_health: {
                type: Type.INTEGER,
                description: 'Estimated % of Right Health Bar (Player 2/Enemy)',
              },
              my_pos: {
                type: Type.STRING,
                description: 'Position of my character',
              },
              enemy_pos: {
                type: Type.STRING,
                description: 'Position of enemy character',
              },
              speech: {
                type: Type.STRING,
                description: 'The commentary/speech',
              },
              emotion: {type: Type.STRING, description: 'Current emotion'},
              situation: {
                type: Type.STRING,
                description: 'Game situation description',
              },
            },
            required: [
              'time',
              'reasoning',
              'my_health',
              'enemy_health',
              'my_pos',
              'enemy_pos',
              'speech',
              'emotion',
              'situation',
            ],
          },
        },
      },
      required: ['rows'],
    },
  },
  {
    name: 'set_scene_descriptions',
    description:
      'Set scene descriptions for each damage event in the timeline.',
    parameters: {
      type: Type.OBJECT,
      properties: {
        scenes: {
          type: Type.ARRAY,
          items: {
            type: Type.OBJECT,
            properties: {
              timestamp_ms: {
                type: Type.INTEGER,
                description: 'The timestamp in milliseconds from the CSV',
              },
              description: {
                type: Type.STRING,
                description: 'Description of what happened (moves used, situation, etc.)',
              },
            },
            required: ['timestamp_ms', 'description'],
          },
        },
      },
      required: ['scenes'],
    },
  },
];

export default (fnMap) =>
  functions.map((fn) => ({
    ...fn,
    callback: fnMap[fn.name],
  }));