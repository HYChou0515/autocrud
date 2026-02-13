/**
 * AutoCRUD Resource Customization
 * 
 * 在這裡自定義生成的資源配置
 * 此文件不會被 generator 覆蓋
 */

import { resources } from '../generated/resources';
import { z } from 'zod';

// ============================================================================
// Character 自定義
// ============================================================================

const charConfig = resources['character'];
if (charConfig) {
  // 自定義 special_ability 為 textarea
  const specialAbilityField = charConfig.fields.find(f => f.name === 'special_ability');
  if (specialAbilityField) {
    specialAbilityField.variant = { type: 'textarea', rows: 5 };
  }
  
  // 自定義 level 為 slider
  const levelField = charConfig.fields.find(f => f.name === 'level');
  if (levelField) {
    levelField.variant = { 
      type: 'slider', 
      sliderMin: 1, 
      sliderMax: 100 
    };
  }
  
  // 添加額外的 Zod 驗證
  if (charConfig.zodSchema) {
    charConfig.zodSchema = charConfig.zodSchema.extend({
      name: z.string().min(3, '名稱至少需要 3 個字元').max(50, '名稱不能超過 50 個字元'),
      level: z.number().int().min(1).max(100).optional(),
    });
  }
}

// ============================================================================
// Equipment 自定義
// ============================================================================

const equipConfig = resources['equipment'];
if (equipConfig) {
  // 自定義 rarity 為 select（手動添加選項）
  const rarityField = equipConfig.fields.find(f => f.name === 'rarity');
  if (rarityField) {
    rarityField.variant = {
      type: 'select',
      options: [
        { value: '普通', label: '🔵 普通' },
        { value: '稀有', label: '🟢 稀有' },
        { value: '史詩', label: '🟣 史詩' },
        { value: '傳奇', label: '🟠 傳奇' },
        { value: '🚀 AutoCRUD 神器', label: '✨ 🚀 AutoCRUD 神器' },
      ]
    };
  }
  
  // 自定義 special_effect 為 markdown
  const effectField = equipConfig.fields.find(f => f.name === 'special_effect');
  if (effectField) {
    effectField.variant = { type: 'markdown', height: 300 };
  }
  
  // Price 使用 slider
  const priceField = equipConfig.fields.find(f => f.name === 'price');
  if (priceField) {
    priceField.variant = { 
      type: 'slider', 
      sliderMin: 0, 
      sliderMax: 10000, 
      step: 100 
    };
  }
}

// ============================================================================
// Guild 自定義
// ============================================================================

const guildConfig = resources['guild'];
if (guildConfig) {
  // Description 使用 textarea
  const descField = guildConfig.fields.find(f => f.name === 'description');
  if (descField) {
    descField.variant = { type: 'textarea', rows: 4 };
  }
  
  // Treasury 使用 slider
  const treasuryField = guildConfig.fields.find(f => f.name === 'treasury');
  if (treasuryField) {
    treasuryField.variant = { 
      type: 'slider', 
      sliderMin: 0, 
      sliderMax: 1000000, 
      step: 1000 
    };
  }
}

// ============================================================================
// Game Event 自定義
// ============================================================================

const eventConfig = resources['game-event'];
if (eventConfig) {
  // Description 使用 markdown
  const descField = eventConfig.fields.find(f => f.name === 'description');
  if (descField) {
    descField.variant = { type: 'markdown', height: 400 };
  }
}

console.log('✅ Resource customizations applied');
