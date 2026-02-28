/**
 * AutoCRUD Resource Customization
 *
 * 在這裡自定義生成的資源配置。
 * 此文件不會被 generator 覆蓋。
 *
 * 型別安全：field name 由 generator 產生的 union type 約束，
 * 如果後端 API 改名或移除欄位，TypeScript 會報錯。
 */

import type { ResourceCustomizations } from '../generated/resources';

export const customizations: ResourceCustomizations = {
  // 在這裡新增資源自定義，例如：
  // 'my-resource': {
  //   fields: {
  //     'my_field': { variant: { type: 'textarea', rows: 5 } },
  //   },
  // },
};
