import {
  require_dayjs_min
} from "./chunk-5EQW2MGV.js";
import {
  __commonJS
} from "./chunk-G3PMV62Z.js";

// node_modules/.pnpm/dayjs@1.11.19/node_modules/dayjs/locale/zh-tw.js
var require_zh_tw = __commonJS({
  "node_modules/.pnpm/dayjs@1.11.19/node_modules/dayjs/locale/zh-tw.js"(exports, module) {
    !(function(_, e) {
      "object" == typeof exports && "undefined" != typeof module ? module.exports = e(require_dayjs_min()) : "function" == typeof define && define.amd ? define(["dayjs"], e) : (_ = "undefined" != typeof globalThis ? globalThis : _ || self).dayjs_locale_zh_tw = e(_.dayjs);
    })(exports, (function(_) {
      "use strict";
      function e(_2) {
        return _2 && "object" == typeof _2 && "default" in _2 ? _2 : { default: _2 };
      }
      var t = e(_), d = { name: "zh-tw", weekdays: "星期日_星期一_星期二_星期三_星期四_星期五_星期六".split("_"), weekdaysShort: "週日_週一_週二_週三_週四_週五_週六".split("_"), weekdaysMin: "日_一_二_三_四_五_六".split("_"), months: "一月_二月_三月_四月_五月_六月_七月_八月_九月_十月_十一月_十二月".split("_"), monthsShort: "1月_2月_3月_4月_5月_6月_7月_8月_9月_10月_11月_12月".split("_"), ordinal: function(_2, e2) {
        return "W" === e2 ? _2 + "週" : _2 + "日";
      }, formats: { LT: "HH:mm", LTS: "HH:mm:ss", L: "YYYY/MM/DD", LL: "YYYY年M月D日", LLL: "YYYY年M月D日 HH:mm", LLLL: "YYYY年M月D日dddd HH:mm", l: "YYYY/M/D", ll: "YYYY年M月D日", lll: "YYYY年M月D日 HH:mm", llll: "YYYY年M月D日dddd HH:mm" }, relativeTime: { future: "%s內", past: "%s前", s: "幾秒", m: "1 分鐘", mm: "%d 分鐘", h: "1 小時", hh: "%d 小時", d: "1 天", dd: "%d 天", M: "1 個月", MM: "%d 個月", y: "1 年", yy: "%d 年" }, meridiem: function(_2, e2) {
        var t2 = 100 * _2 + e2;
        return t2 < 600 ? "凌晨" : t2 < 900 ? "早上" : t2 < 1100 ? "上午" : t2 < 1300 ? "中午" : t2 < 1800 ? "下午" : "晚上";
      } };
      return t.default.locale(d, null, true), d;
    }));
  }
});
export default require_zh_tw();
//# sourceMappingURL=dayjs_locale_zh-tw.js.map
