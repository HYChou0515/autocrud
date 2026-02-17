import {
  require_dayjs_min
} from "./chunk-5EQW2MGV.js";
import {
  AccordionChevron,
  ActionIcon,
  Box,
  CheckIcon,
  CloseButton,
  Input,
  InputBase,
  Modal,
  Popover,
  UnstyledButton,
  clsx_default,
  createVarsResolver,
  factory,
  getFontSize,
  getSize,
  getSpacing,
  useInputProps,
  useProps,
  useResolvedStylesApi,
  useStyles
} from "./chunk-BSJUYPHC.js";
import {
  clamp,
  useClickOutside,
  useDidUpdate,
  useDisclosure,
  useMergedRef,
  useUncontrolled
} from "./chunk-PLI3YFLS.js";
import {
  require_jsx_runtime
} from "./chunk-LBEETZ2E.js";
import {
  require_react
} from "./chunk-OELA7GPI.js";
import {
  __commonJS,
  __toESM
} from "./chunk-G3PMV62Z.js";

// node_modules/.pnpm/dayjs@1.11.19/node_modules/dayjs/plugin/timezone.js
var require_timezone = __commonJS({
  "node_modules/.pnpm/dayjs@1.11.19/node_modules/dayjs/plugin/timezone.js"(exports, module) {
    !(function(t, e) {
      "object" == typeof exports && "undefined" != typeof module ? module.exports = e() : "function" == typeof define && define.amd ? define(e) : (t = "undefined" != typeof globalThis ? globalThis : t || self).dayjs_plugin_timezone = e();
    })(exports, (function() {
      "use strict";
      var t = { year: 0, month: 1, day: 2, hour: 3, minute: 4, second: 5 }, e = {};
      return function(n, i, o) {
        var r, a = function(t2, n2, i2) {
          void 0 === i2 && (i2 = {});
          var o2 = new Date(t2), r2 = (function(t3, n3) {
            void 0 === n3 && (n3 = {});
            var i3 = n3.timeZoneName || "short", o3 = t3 + "|" + i3, r3 = e[o3];
            return r3 || (r3 = new Intl.DateTimeFormat("en-US", { hour12: false, timeZone: t3, year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZoneName: i3 }), e[o3] = r3), r3;
          })(n2, i2);
          return r2.formatToParts(o2);
        }, u = function(e2, n2) {
          for (var i2 = a(e2, n2), r2 = [], u2 = 0; u2 < i2.length; u2 += 1) {
            var f2 = i2[u2], s2 = f2.type, m = f2.value, c = t[s2];
            c >= 0 && (r2[c] = parseInt(m, 10));
          }
          var d = r2[3], l = 24 === d ? 0 : d, h = r2[0] + "-" + r2[1] + "-" + r2[2] + " " + l + ":" + r2[4] + ":" + r2[5] + ":000", v = +e2;
          return (o.utc(h).valueOf() - (v -= v % 1e3)) / 6e4;
        }, f = i.prototype;
        f.tz = function(t2, e2) {
          void 0 === t2 && (t2 = r);
          var n2, i2 = this.utcOffset(), a2 = this.toDate(), u2 = a2.toLocaleString("en-US", { timeZone: t2 }), f2 = Math.round((a2 - new Date(u2)) / 1e3 / 60), s2 = 15 * -Math.round(a2.getTimezoneOffset() / 15) - f2;
          if (!Number(s2)) n2 = this.utcOffset(0, e2);
          else if (n2 = o(u2, { locale: this.$L }).$set("millisecond", this.$ms).utcOffset(s2, true), e2) {
            var m = n2.utcOffset();
            n2 = n2.add(i2 - m, "minute");
          }
          return n2.$x.$timezone = t2, n2;
        }, f.offsetName = function(t2) {
          var e2 = this.$x.$timezone || o.tz.guess(), n2 = a(this.valueOf(), e2, { timeZoneName: t2 }).find((function(t3) {
            return "timezonename" === t3.type.toLowerCase();
          }));
          return n2 && n2.value;
        };
        var s = f.startOf;
        f.startOf = function(t2, e2) {
          if (!this.$x || !this.$x.$timezone) return s.call(this, t2, e2);
          var n2 = o(this.format("YYYY-MM-DD HH:mm:ss:SSS"), { locale: this.$L });
          return s.call(n2, t2, e2).tz(this.$x.$timezone, true);
        }, o.tz = function(t2, e2, n2) {
          var i2 = n2 && e2, a2 = n2 || e2 || r, f2 = u(+o(), a2);
          if ("string" != typeof t2) return o(t2).tz(a2);
          var s2 = (function(t3, e3, n3) {
            var i3 = t3 - 60 * e3 * 1e3, o2 = u(i3, n3);
            if (e3 === o2) return [i3, e3];
            var r2 = u(i3 -= 60 * (o2 - e3) * 1e3, n3);
            return o2 === r2 ? [i3, o2] : [t3 - 60 * Math.min(o2, r2) * 1e3, Math.max(o2, r2)];
          })(o.utc(t2, i2).valueOf(), f2, a2), m = s2[0], c = s2[1], d = o(m).utcOffset(c);
          return d.$x.$timezone = a2, d;
        }, o.tz.guess = function() {
          return Intl.DateTimeFormat().resolvedOptions().timeZone;
        }, o.tz.setDefault = function(t2) {
          r = t2;
        };
      };
    }));
  }
});

// node_modules/.pnpm/dayjs@1.11.19/node_modules/dayjs/plugin/utc.js
var require_utc = __commonJS({
  "node_modules/.pnpm/dayjs@1.11.19/node_modules/dayjs/plugin/utc.js"(exports, module) {
    !(function(t, i) {
      "object" == typeof exports && "undefined" != typeof module ? module.exports = i() : "function" == typeof define && define.amd ? define(i) : (t = "undefined" != typeof globalThis ? globalThis : t || self).dayjs_plugin_utc = i();
    })(exports, (function() {
      "use strict";
      var t = "minute", i = /[+-]\d\d(?::?\d\d)?/g, e = /([+-]|\d\d)/g;
      return function(s, f, n) {
        var u = f.prototype;
        n.utc = function(t2) {
          var i2 = { date: t2, utc: true, args: arguments };
          return new f(i2);
        }, u.utc = function(i2) {
          var e2 = n(this.toDate(), { locale: this.$L, utc: true });
          return i2 ? e2.add(this.utcOffset(), t) : e2;
        }, u.local = function() {
          return n(this.toDate(), { locale: this.$L, utc: false });
        };
        var r = u.parse;
        u.parse = function(t2) {
          t2.utc && (this.$u = true), this.$utils().u(t2.$offset) || (this.$offset = t2.$offset), r.call(this, t2);
        };
        var o = u.init;
        u.init = function() {
          if (this.$u) {
            var t2 = this.$d;
            this.$y = t2.getUTCFullYear(), this.$M = t2.getUTCMonth(), this.$D = t2.getUTCDate(), this.$W = t2.getUTCDay(), this.$H = t2.getUTCHours(), this.$m = t2.getUTCMinutes(), this.$s = t2.getUTCSeconds(), this.$ms = t2.getUTCMilliseconds();
          } else o.call(this);
        };
        var a = u.utcOffset;
        u.utcOffset = function(s2, f2) {
          var n2 = this.$utils().u;
          if (n2(s2)) return this.$u ? 0 : n2(this.$offset) ? a.call(this) : this.$offset;
          if ("string" == typeof s2 && (s2 = (function(t2) {
            void 0 === t2 && (t2 = "");
            var s3 = t2.match(i);
            if (!s3) return null;
            var f3 = ("" + s3[0]).match(e) || ["-", 0, 0], n3 = f3[0], u3 = 60 * +f3[1] + +f3[2];
            return 0 === u3 ? 0 : "+" === n3 ? u3 : -u3;
          })(s2), null === s2)) return this;
          var u2 = Math.abs(s2) <= 16 ? 60 * s2 : s2;
          if (0 === u2) return this.utc(f2);
          var r2 = this.clone();
          if (f2) return r2.$offset = u2, r2.$u = false, r2;
          var o2 = this.$u ? this.toDate().getTimezoneOffset() : -1 * this.utcOffset();
          return (r2 = this.local().add(u2 + o2, t)).$offset = u2, r2.$x.$localOffset = o2, r2;
        };
        var h = u.format;
        u.format = function(t2) {
          var i2 = t2 || (this.$u ? "YYYY-MM-DDTHH:mm:ss[Z]" : "");
          return h.call(this, i2);
        }, u.valueOf = function() {
          var t2 = this.$utils().u(this.$offset) ? 0 : this.$offset + (this.$x.$localOffset || this.$d.getTimezoneOffset());
          return this.$d.valueOf() - 6e4 * t2;
        }, u.isUTC = function() {
          return !!this.$u;
        }, u.toISOString = function() {
          return this.toDate().toISOString();
        }, u.toString = function() {
          return this.toDate().toUTCString();
        };
        var l = u.toDate;
        u.toDate = function(t2) {
          return "s" === t2 && this.$offset ? n(this.format("YYYY-MM-DD HH:mm:ss:SSS")).toDate() : l.call(this);
        };
        var c = u.diff;
        u.diff = function(t2, i2, e2) {
          if (t2 && this.$u === t2.$u) return c.call(this, t2, i2, e2);
          var s2 = this.local(), f2 = n(t2).local();
          return c.call(s2, f2, i2, e2);
        };
      };
    }));
  }
});

// node_modules/.pnpm/dayjs@1.11.19/node_modules/dayjs/plugin/isoWeek.js
var require_isoWeek = __commonJS({
  "node_modules/.pnpm/dayjs@1.11.19/node_modules/dayjs/plugin/isoWeek.js"(exports, module) {
    !(function(e, t) {
      "object" == typeof exports && "undefined" != typeof module ? module.exports = t() : "function" == typeof define && define.amd ? define(t) : (e = "undefined" != typeof globalThis ? globalThis : e || self).dayjs_plugin_isoWeek = t();
    })(exports, (function() {
      "use strict";
      var e = "day";
      return function(t, i, s) {
        var a = function(t2) {
          return t2.add(4 - t2.isoWeekday(), e);
        }, d = i.prototype;
        d.isoWeekYear = function() {
          return a(this).year();
        }, d.isoWeek = function(t2) {
          if (!this.$utils().u(t2)) return this.add(7 * (t2 - this.isoWeek()), e);
          var i2, d2, n2, o, r = a(this), u = (i2 = this.isoWeekYear(), d2 = this.$u, n2 = (d2 ? s.utc : s)().year(i2).startOf("year"), o = 4 - n2.isoWeekday(), n2.isoWeekday() > 4 && (o += 7), n2.add(o, e));
          return r.diff(u, "week") + 1;
        }, d.isoWeekday = function(e2) {
          return this.$utils().u(e2) ? this.day() || 7 : this.day(this.day() % 7 ? e2 : e2 - 7);
        };
        var n = d.startOf;
        d.startOf = function(e2, t2) {
          var i2 = this.$utils(), s2 = !!i2.u(t2) || t2;
          return "isoweek" === i2.p(e2) ? s2 ? this.date(this.date() - (this.isoWeekday() - 1)).startOf("day") : this.date(this.date() - 1 - (this.isoWeekday() - 1) + 7).endOf("day") : n.bind(this)(e2, t2);
        };
      };
    }));
  }
});

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/utils/get-formatted-date.mjs
var import_dayjs = __toESM(require_dayjs_min(), 1);
function defaultDateFormatter({
  type,
  date,
  locale,
  format,
  labelSeparator
}) {
  const formatDate = (value) => (0, import_dayjs.default)(value).locale(locale).format(format);
  if (type === "default") {
    return date === null ? "" : formatDate(date);
  }
  if (type === "multiple") {
    return date.map(formatDate).join(", ");
  }
  if (type === "range" && Array.isArray(date)) {
    if (date[0] && date[1]) {
      return `${formatDate(date[0])} ${labelSeparator} ${formatDate(date[1])}`;
    }
    if (date[0]) {
      return `${formatDate(date[0])} ${labelSeparator} `;
    }
    return "";
  }
  return "";
}
function getFormattedDate({ formatter, ...others }) {
  return (formatter || defaultDateFormatter)(others);
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/utils/handle-control-key-down.mjs
function getNextIndex({ direction, levelIndex, rowIndex, cellIndex, size }) {
  switch (direction) {
    case "up":
      if (levelIndex === 0 && rowIndex === 0) {
        return null;
      }
      if (rowIndex === 0) {
        return {
          levelIndex: levelIndex - 1,
          rowIndex: cellIndex <= size[levelIndex - 1][size[levelIndex - 1].length - 1] - 1 ? size[levelIndex - 1].length - 1 : size[levelIndex - 1].length - 2,
          cellIndex
        };
      }
      return {
        levelIndex,
        rowIndex: rowIndex - 1,
        cellIndex
      };
    case "down":
      if (rowIndex === size[levelIndex].length - 1) {
        return {
          levelIndex: levelIndex + 1,
          rowIndex: 0,
          cellIndex
        };
      }
      if (rowIndex === size[levelIndex].length - 2 && cellIndex >= size[levelIndex][size[levelIndex].length - 1]) {
        return {
          levelIndex: levelIndex + 1,
          rowIndex: 0,
          cellIndex
        };
      }
      return {
        levelIndex,
        rowIndex: rowIndex + 1,
        cellIndex
      };
    case "left":
      if (levelIndex === 0 && rowIndex === 0 && cellIndex === 0) {
        return null;
      }
      if (rowIndex === 0 && cellIndex === 0) {
        return {
          levelIndex: levelIndex - 1,
          rowIndex: size[levelIndex - 1].length - 1,
          cellIndex: size[levelIndex - 1][size[levelIndex - 1].length - 1] - 1
        };
      }
      if (cellIndex === 0) {
        return {
          levelIndex,
          rowIndex: rowIndex - 1,
          cellIndex: size[levelIndex][rowIndex - 1] - 1
        };
      }
      return {
        levelIndex,
        rowIndex,
        cellIndex: cellIndex - 1
      };
    case "right":
      if (rowIndex === size[levelIndex].length - 1 && cellIndex === size[levelIndex][rowIndex] - 1) {
        return {
          levelIndex: levelIndex + 1,
          rowIndex: 0,
          cellIndex: 0
        };
      }
      if (cellIndex === size[levelIndex][rowIndex] - 1) {
        return {
          levelIndex,
          rowIndex: rowIndex + 1,
          cellIndex: 0
        };
      }
      return {
        levelIndex,
        rowIndex,
        cellIndex: cellIndex + 1
      };
    default:
      return { levelIndex, rowIndex, cellIndex };
  }
}
function focusOnNextFocusableControl({
  controlsRef,
  direction,
  levelIndex,
  rowIndex,
  cellIndex,
  size
}) {
  var _a, _b, _c;
  const nextIndex = getNextIndex({ direction, size, rowIndex, cellIndex, levelIndex });
  if (!nextIndex) {
    return;
  }
  const controlToFocus = (_c = (_b = (_a = controlsRef.current) == null ? void 0 : _a[nextIndex.levelIndex]) == null ? void 0 : _b[nextIndex.rowIndex]) == null ? void 0 : _c[nextIndex.cellIndex];
  if (!controlToFocus) {
    return;
  }
  if (controlToFocus.disabled || controlToFocus.getAttribute("data-hidden") || controlToFocus.getAttribute("data-outside")) {
    focusOnNextFocusableControl({
      controlsRef,
      direction,
      levelIndex: nextIndex.levelIndex,
      cellIndex: nextIndex.cellIndex,
      rowIndex: nextIndex.rowIndex,
      size
    });
  } else {
    controlToFocus.focus();
  }
}
function getDirection(key) {
  switch (key) {
    case "ArrowDown":
      return "down";
    case "ArrowUp":
      return "up";
    case "ArrowRight":
      return "right";
    case "ArrowLeft":
      return "left";
    default:
      return null;
  }
}
function getControlsSize(controlsRef) {
  var _a;
  return (_a = controlsRef.current) == null ? void 0 : _a.map((column) => column.map((row) => row.length));
}
function handleControlKeyDown({
  controlsRef,
  levelIndex,
  rowIndex,
  cellIndex,
  event
}) {
  const direction = getDirection(event.key);
  if (direction) {
    event.preventDefault();
    const size = getControlsSize(controlsRef);
    focusOnNextFocusableControl({
      controlsRef,
      direction,
      levelIndex,
      rowIndex,
      cellIndex,
      size
    });
  }
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/utils/assign-time/assign-time.mjs
function assignTime(originalDate, resultDate) {
  if (!originalDate || !resultDate) {
    return resultDate;
  }
  const hours = originalDate.getHours();
  const minutes = originalDate.getMinutes();
  const seconds = originalDate.getSeconds();
  const ms = originalDate.getMilliseconds();
  const result = new Date(resultDate);
  result.setHours(hours);
  result.setMinutes(minutes);
  result.setSeconds(seconds);
  result.setMilliseconds(ms);
  return result;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/utils/get-default-clamped-date.mjs
var import_dayjs4 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/utils/shift-timezone.mjs
var import_dayjs3 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/utils/get-timezone-offset.mjs
var import_dayjs2 = __toESM(require_dayjs_min(), 1);
var import_timezone = __toESM(require_timezone(), 1);
var import_utc = __toESM(require_utc(), 1);
import_dayjs2.default.extend(import_utc.default);
import_dayjs2.default.extend(import_timezone.default);
function getTimezoneOffset(date, timezone) {
  if (timezone) {
    return (0, import_dayjs2.default)(date).tz(timezone).utcOffset() + date.getTimezoneOffset();
  }
  return 0;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/utils/shift-timezone.mjs
var updateTimezone = (date, timezone, direction) => {
  if (!date) {
    return null;
  }
  if (!timezone) {
    return date;
  }
  let offset = getTimezoneOffset(date, timezone);
  if (direction === "remove") {
    offset *= -1;
  }
  return (0, import_dayjs3.default)(date).add(offset, "minutes").toDate();
};
function shiftTimezone(direction, date, timezone, disabled) {
  if (disabled || !date) {
    return date;
  }
  if (Array.isArray(date)) {
    return date.map((d) => updateTimezone(d, timezone, direction));
  }
  return updateTimezone(date, timezone, direction);
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/utils/get-default-clamped-date.mjs
function getDefaultClampedDate({ minDate, maxDate, timezone }) {
  const today = shiftTimezone("add", /* @__PURE__ */ new Date(), timezone);
  if (!minDate && !maxDate) {
    return today;
  }
  if (minDate && (0, import_dayjs4.default)(today).isBefore(minDate)) {
    return minDate;
  }
  if (maxDate && (0, import_dayjs4.default)(today).isAfter(maxDate)) {
    return maxDate;
  }
  return today;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DatesProvider/DatesProvider.mjs
var import_jsx_runtime = __toESM(require_jsx_runtime(), 1);
var import_react = __toESM(require_react(), 1);
var DATES_PROVIDER_DEFAULT_SETTINGS = {
  locale: "en",
  timezone: null,
  firstDayOfWeek: 1,
  weekendDays: [0, 6],
  labelSeparator: "–",
  consistentWeeks: false
};
var DatesProviderContext = (0, import_react.createContext)(DATES_PROVIDER_DEFAULT_SETTINGS);
function DatesProvider({ settings, children }) {
  return (0, import_jsx_runtime.jsx)(DatesProviderContext.Provider, { value: { ...DATES_PROVIDER_DEFAULT_SETTINGS, ...settings }, children });
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DatesProvider/use-dates-context.mjs
var import_react2 = __toESM(require_react(), 1);
function useDatesContext() {
  const ctx = (0, import_react2.useContext)(DatesProviderContext);
  const getLocale = (0, import_react2.useCallback)((input) => input || ctx.locale, [ctx.locale]);
  const getTimezone = (0, import_react2.useCallback)(
    (input) => input || ctx.timezone || void 0,
    [ctx.timezone]
  );
  const getFirstDayOfWeek = (0, import_react2.useCallback)(
    (input) => typeof input === "number" ? input : ctx.firstDayOfWeek,
    [ctx.firstDayOfWeek]
  );
  const getWeekendDays = (0, import_react2.useCallback)(
    (input) => Array.isArray(input) ? input : ctx.weekendDays,
    [ctx.weekendDays]
  );
  const getLabelSeparator = (0, import_react2.useCallback)(
    (input) => typeof input === "string" ? input : ctx.labelSeparator,
    [ctx.labelSeparator]
  );
  return {
    ...ctx,
    getLocale,
    getTimezone,
    getFirstDayOfWeek,
    getWeekendDays,
    getLabelSeparator
  };
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/HiddenDatesInput/HiddenDatesInput.mjs
var import_jsx_runtime2 = __toESM(require_jsx_runtime(), 1);
var import_dayjs5 = __toESM(require_dayjs_min(), 1);
function formatValue(value, type) {
  const ctx = useDatesContext();
  const formatDateWithTimezone = (date) => {
    return shiftTimezone("remove", date, ctx.getTimezone()).toISOString();
  };
  if (type === "range" && Array.isArray(value)) {
    const [startDate, endDate] = value;
    if (!startDate) {
      return "";
    }
    if (!endDate) {
      return `${formatDateWithTimezone(startDate)} –`;
    }
    return `${formatDateWithTimezone(startDate)} – ${formatDateWithTimezone(endDate)}`;
  }
  if (type === "multiple" && Array.isArray(value)) {
    return value.map((date) => date && formatDateWithTimezone(date)).filter(Boolean).join(", ");
  }
  if (!Array.isArray(value) && value) {
    return formatDateWithTimezone(value);
  }
  return "";
}
function HiddenDatesInput({ value, type, name, form }) {
  return (0, import_jsx_runtime2.jsx)("input", { type: "hidden", value: formatValue(value, type), name, form });
}
HiddenDatesInput.displayName = "@mantine/dates/HiddenDatesInput";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/TimeInput/TimeInput.mjs
var import_jsx_runtime3 = __toESM(require_jsx_runtime(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/TimeInput/TimeInput.module.css.mjs
var classes = { "input": "m_468e7eda" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/TimeInput/TimeInput.mjs
var defaultProps = {};
var TimeInput = factory((_props, ref) => {
  const props = useProps("TimeInput", defaultProps, _props);
  const {
    classNames,
    styles,
    unstyled,
    vars,
    withSeconds,
    minTime,
    maxTime,
    value,
    onChange,
    step,
    ...others
  } = props;
  const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
    classNames,
    styles,
    props
  });
  const checkIfTimeLimitExceeded = (val) => {
    if (minTime !== void 0 || maxTime !== void 0) {
      const [hours, minutes, seconds] = val.split(":").map(Number);
      if (minTime) {
        const [minHours, minMinutes, minSeconds] = minTime.split(":").map(Number);
        if (hours < minHours || hours === minHours && minutes < minMinutes || withSeconds && hours === minHours && minutes === minMinutes && seconds < minSeconds) {
          return -1;
        }
      }
      if (maxTime) {
        const [maxHours, maxMinutes, maxSeconds] = maxTime.split(":").map(Number);
        if (hours > maxHours || hours === maxHours && minutes > maxMinutes || withSeconds && hours === maxHours && minutes === maxMinutes && seconds > maxSeconds) {
          return 1;
        }
      }
    }
    return 0;
  };
  const onTimeBlur = (event) => {
    var _a, _b, _c;
    (_a = props.onBlur) == null ? void 0 : _a.call(props, event);
    if (minTime !== void 0 || maxTime !== void 0) {
      const val = event.currentTarget.value;
      if (val) {
        const check = checkIfTimeLimitExceeded(val);
        if (check === 1) {
          event.currentTarget.value = maxTime;
          (_b = props.onChange) == null ? void 0 : _b.call(props, event);
        } else if (check === -1) {
          event.currentTarget.value = minTime;
          (_c = props.onChange) == null ? void 0 : _c.call(props, event);
        }
      }
    }
  };
  return (0, import_jsx_runtime3.jsx)(
    InputBase,
    {
      classNames: { ...resolvedClassNames, input: clsx_default(classes.input, resolvedClassNames == null ? void 0 : resolvedClassNames.input) },
      styles: resolvedStyles,
      unstyled,
      ref,
      value,
      step: step ?? (withSeconds ? 1 : 60),
      ...others,
      onChange,
      onBlur: onTimeBlur,
      type: "time",
      __staticSelector: "TimeInput"
    }
  );
});
TimeInput.classes = InputBase.classes;
TimeInput.displayName = "@mantine/dates/TimeInput";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Day/Day.mjs
var import_jsx_runtime4 = __toESM(require_jsx_runtime(), 1);
var import_dayjs6 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Day/Day.module.css.mjs
var classes2 = { "day": "m_396ce5cb" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Day/Day.mjs
var defaultProps2 = {};
var varsResolver = createVarsResolver((_, { size }) => ({
  day: {
    "--day-size": getSize(size, "day-size")
  }
}));
var Day = factory((_props, ref) => {
  const props = useProps("Day", defaultProps2, _props);
  const {
    classNames,
    className,
    style,
    styles,
    unstyled,
    vars,
    date,
    disabled,
    __staticSelector,
    weekend,
    outside,
    selected,
    renderDay,
    inRange,
    firstInRange,
    lastInRange,
    hidden,
    static: isStatic,
    highlightToday,
    ...others
  } = props;
  const getStyles = useStyles({
    name: __staticSelector || "Day",
    classes: classes2,
    props,
    className,
    style,
    classNames,
    styles,
    unstyled,
    vars,
    varsResolver,
    rootSelector: "day"
  });
  const ctx = useDatesContext();
  return (0, import_jsx_runtime4.jsx)(
    UnstyledButton,
    {
      ...getStyles("day", { style: hidden ? { display: "none" } : void 0 }),
      component: isStatic ? "div" : "button",
      ref,
      disabled,
      "data-today": (0, import_dayjs6.default)(date).isSame(shiftTimezone("add", /* @__PURE__ */ new Date(), ctx.getTimezone()), "day") || void 0,
      "data-hidden": hidden || void 0,
      "data-highlight-today": highlightToday || void 0,
      "data-disabled": disabled || void 0,
      "data-weekend": !disabled && !outside && weekend || void 0,
      "data-outside": !disabled && outside || void 0,
      "data-selected": !disabled && selected || void 0,
      "data-in-range": inRange && !disabled || void 0,
      "data-first-in-range": firstInRange && !disabled || void 0,
      "data-last-in-range": lastInRange && !disabled || void 0,
      "data-static": isStatic || void 0,
      unstyled,
      ...others,
      children: (renderDay == null ? void 0 : renderDay(date)) || (0, import_dayjs6.default)(date).date()
    }
  );
});
Day.classes = classes2;
Day.displayName = "@mantine/dates/Day";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/WeekdaysRow/WeekdaysRow.mjs
var import_jsx_runtime5 = __toESM(require_jsx_runtime(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/WeekdaysRow/get-weekdays-names/get-weekdays-names.mjs
var import_dayjs7 = __toESM(require_dayjs_min(), 1);
function getWeekdayNames({
  locale,
  format = "dd",
  firstDayOfWeek = 1
}) {
  const baseDate = (0, import_dayjs7.default)().day(firstDayOfWeek);
  const labels = [];
  for (let i = 0; i < 7; i += 1) {
    if (typeof format === "string") {
      labels.push((0, import_dayjs7.default)(baseDate).add(i, "days").locale(locale).format(format));
    } else {
      labels.push(format((0, import_dayjs7.default)(baseDate).add(i, "days").toDate()));
    }
  }
  return labels;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/WeekdaysRow/WeekdaysRow.module.css.mjs
var classes3 = { "weekday": "m_18a3eca" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/WeekdaysRow/WeekdaysRow.mjs
var defaultProps3 = {};
var varsResolver2 = createVarsResolver((_, { size }) => ({
  weekdaysRow: {
    "--wr-fz": getFontSize(size),
    "--wr-spacing": getSpacing(size)
  }
}));
var WeekdaysRow = factory((_props, ref) => {
  const props = useProps("WeekdaysRow", defaultProps3, _props);
  const {
    classNames,
    className,
    style,
    styles,
    unstyled,
    vars,
    locale,
    firstDayOfWeek,
    weekdayFormat,
    cellComponent: CellComponent = "th",
    __staticSelector,
    withWeekNumbers,
    ...others
  } = props;
  const getStyles = useStyles({
    name: __staticSelector || "WeekdaysRow",
    classes: classes3,
    props,
    className,
    style,
    classNames,
    styles,
    unstyled,
    vars,
    varsResolver: varsResolver2,
    rootSelector: "weekdaysRow"
  });
  const ctx = useDatesContext();
  const weekdays = getWeekdayNames({
    locale: ctx.getLocale(locale),
    format: weekdayFormat,
    firstDayOfWeek: ctx.getFirstDayOfWeek(firstDayOfWeek)
  }).map((weekday, index) => (0, import_jsx_runtime5.jsx)(CellComponent, { ...getStyles("weekday"), children: weekday }, index));
  return (0, import_jsx_runtime5.jsxs)(Box, { component: "tr", ref, ...getStyles("weekdaysRow"), ...others, children: [
    withWeekNumbers && (0, import_jsx_runtime5.jsx)(CellComponent, { ...getStyles("weekday"), children: "#" }),
    weekdays
  ] });
});
WeekdaysRow.classes = classes3;
WeekdaysRow.displayName = "@mantine/dates/WeekdaysRow";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/get-end-of-week/get-end-of-week.mjs
var import_dayjs8 = __toESM(require_dayjs_min(), 1);
function getEndOfWeek(date, firstDayOfWeek = 1) {
  let value = (0, import_dayjs8.default)(date);
  const lastDayOfWeek = firstDayOfWeek === 0 ? 6 : firstDayOfWeek - 1;
  while (value.day() !== lastDayOfWeek) {
    value = value.add(1, "day");
  }
  return value.toDate();
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/get-start-of-week/get-start-of-week.mjs
var import_dayjs9 = __toESM(require_dayjs_min(), 1);
function getStartOfWeek(date, firstDayOfWeek = 1) {
  let value = (0, import_dayjs9.default)(date);
  while (value.day() !== firstDayOfWeek) {
    value = value.subtract(1, "day");
  }
  return value.toDate();
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/get-month-days/get-month-days.mjs
var import_dayjs10 = __toESM(require_dayjs_min(), 1);
function getMonthDays({
  month,
  firstDayOfWeek = 1,
  consistentWeeks
}) {
  const day = (0, import_dayjs10.default)(month).subtract((0, import_dayjs10.default)(month).date() - 1, "day");
  const start = (0, import_dayjs10.default)(day).startOf("day");
  const startOfMonth = start.toDate();
  const endOfMonth = start.add(+start.daysInMonth() - 1, "day").toDate();
  const endDate = getEndOfWeek(endOfMonth, firstDayOfWeek);
  const date = getStartOfWeek(startOfMonth, firstDayOfWeek);
  const weeks = [];
  while (date <= endDate) {
    const days = [];
    for (let i = 0; i < 7; i += 1) {
      days.push(new Date(date));
      date.setDate(date.getDate() + 1);
    }
    weeks.push(days);
  }
  if (consistentWeeks && weeks.length < 6) {
    const lastWeek = weeks[weeks.length - 1];
    const lastDay = lastWeek[lastWeek.length - 1];
    const nextDay = new Date(lastDay);
    nextDay.setDate(nextDay.getDate() + 1);
    while (weeks.length < 6) {
      const days = [];
      for (let i = 0; i < 7; i += 1) {
        days.push(new Date(nextDay));
        nextDay.setDate(nextDay.getDate() + 1);
      }
      weeks.push(days);
    }
  }
  return weeks;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/is-same-month/is-same-month.mjs
var import_dayjs11 = __toESM(require_dayjs_min(), 1);
function isSameMonth(date, comparison) {
  return (0, import_dayjs11.default)(date).format("YYYY-MM") === (0, import_dayjs11.default)(comparison).format("YYYY-MM");
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/Month.mjs
var import_jsx_runtime6 = __toESM(require_jsx_runtime(), 1);
var import_dayjs16 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/get-date-in-tab-order/get-date-in-tab-order.mjs
var import_dayjs14 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/is-after-min-date/is-after-min-date.mjs
var import_dayjs12 = __toESM(require_dayjs_min(), 1);
function isAfterMinDate(date, minDate) {
  return minDate instanceof Date ? (0, import_dayjs12.default)(date).isAfter((0, import_dayjs12.default)(minDate).subtract(1, "day"), "day") : true;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/is-before-max-date/is-before-max-date.mjs
var import_dayjs13 = __toESM(require_dayjs_min(), 1);
function isBeforeMaxDate(date, maxDate) {
  return maxDate instanceof Date ? (0, import_dayjs13.default)(date).isBefore((0, import_dayjs13.default)(maxDate).add(1, "day"), "day") : true;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/get-date-in-tab-order/get-date-in-tab-order.mjs
function getDateInTabOrder(dates, minDate, maxDate, getDateControlProps, excludeDate, hideOutsideDates, month) {
  const enabledDates = dates.flat().filter(
    (date) => {
      var _a;
      return isBeforeMaxDate(date, maxDate) && isAfterMinDate(date, minDate) && !(excludeDate == null ? void 0 : excludeDate(date)) && !((_a = getDateControlProps == null ? void 0 : getDateControlProps(date)) == null ? void 0 : _a.disabled) && (!hideOutsideDates || isSameMonth(date, month));
    }
  );
  const selectedDate = enabledDates.find((date) => {
    var _a;
    return (_a = getDateControlProps == null ? void 0 : getDateControlProps(date)) == null ? void 0 : _a.selected;
  });
  if (selectedDate) {
    return selectedDate;
  }
  const currentDate = enabledDates.find((date) => (0, import_dayjs14.default)().isSame(date, "date"));
  if (currentDate) {
    return currentDate;
  }
  return enabledDates[0];
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/get-week-number/get-week-number.mjs
var import_dayjs15 = __toESM(require_dayjs_min(), 1);
var import_isoWeek = __toESM(require_isoWeek(), 1);
import_dayjs15.default.extend(import_isoWeek.default);
function getWeekNumber(week) {
  const monday = week.find((date) => (0, import_dayjs15.default)(date).day() === 1);
  return (0, import_dayjs15.default)(monday).isoWeek();
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/Month.module.css.mjs
var classes4 = { "month": "m_cc9820d3", "monthCell": "m_8f457cd5", "weekNumber": "m_6cff9dea" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Month/Month.mjs
var defaultProps4 = {
  withCellSpacing: true
};
var varsResolver3 = createVarsResolver((_, { size }) => ({
  weekNumber: {
    "--wn-fz": getFontSize(size),
    "--wn-size": getSize(size, "wn-size")
  }
}));
var Month = factory((_props, ref) => {
  const props = useProps("Month", defaultProps4, _props);
  const {
    classNames,
    className,
    style,
    styles,
    unstyled,
    vars,
    __staticSelector,
    locale,
    firstDayOfWeek,
    weekdayFormat,
    month,
    weekendDays,
    getDayProps,
    excludeDate,
    minDate,
    maxDate,
    renderDay,
    hideOutsideDates,
    hideWeekdays,
    getDayAriaLabel,
    static: isStatic,
    __getDayRef,
    __onDayKeyDown,
    __onDayClick,
    __onDayMouseEnter,
    __preventFocus,
    __stopPropagation,
    withCellSpacing,
    size,
    highlightToday,
    withWeekNumbers,
    ...others
  } = props;
  const getStyles = useStyles({
    name: __staticSelector || "Month",
    classes: classes4,
    props,
    className,
    style,
    classNames,
    styles,
    unstyled,
    vars,
    varsResolver: varsResolver3,
    rootSelector: "month"
  });
  const ctx = useDatesContext();
  const dates = getMonthDays({
    month,
    firstDayOfWeek: ctx.getFirstDayOfWeek(firstDayOfWeek),
    consistentWeeks: ctx.consistentWeeks
  });
  const dateInTabOrder = getDateInTabOrder(
    dates,
    minDate,
    maxDate,
    getDayProps,
    excludeDate,
    hideOutsideDates,
    month
  );
  const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
    classNames,
    styles,
    props
  });
  const rows = dates.map((row, rowIndex) => {
    const cells = row.map((date, cellIndex) => {
      const outside = !isSameMonth(date, month);
      const ariaLabel = (getDayAriaLabel == null ? void 0 : getDayAriaLabel(date)) || (0, import_dayjs16.default)(date).locale(locale || ctx.locale).format("D MMMM YYYY");
      const dayProps = getDayProps == null ? void 0 : getDayProps(date);
      const isDateInTabOrder = (0, import_dayjs16.default)(date).isSame(dateInTabOrder, "date");
      return (0, import_jsx_runtime6.jsx)(
        "td",
        {
          ...getStyles("monthCell"),
          "data-with-spacing": withCellSpacing || void 0,
          children: (0, import_jsx_runtime6.jsx)(
            Day,
            {
              __staticSelector: __staticSelector || "Month",
              classNames: resolvedClassNames,
              styles: resolvedStyles,
              unstyled,
              "data-mantine-stop-propagation": __stopPropagation || void 0,
              highlightToday,
              renderDay,
              date,
              size,
              weekend: ctx.getWeekendDays(weekendDays).includes(date.getDay()),
              outside,
              hidden: hideOutsideDates ? outside : false,
              "aria-label": ariaLabel,
              static: isStatic,
              disabled: (excludeDate == null ? void 0 : excludeDate(date)) || !isBeforeMaxDate(date, maxDate) || !isAfterMinDate(date, minDate),
              ref: (node) => __getDayRef == null ? void 0 : __getDayRef(rowIndex, cellIndex, node),
              ...dayProps,
              onKeyDown: (event) => {
                var _a;
                (_a = dayProps == null ? void 0 : dayProps.onKeyDown) == null ? void 0 : _a.call(dayProps, event);
                __onDayKeyDown == null ? void 0 : __onDayKeyDown(event, { rowIndex, cellIndex, date });
              },
              onMouseEnter: (event) => {
                var _a;
                (_a = dayProps == null ? void 0 : dayProps.onMouseEnter) == null ? void 0 : _a.call(dayProps, event);
                __onDayMouseEnter == null ? void 0 : __onDayMouseEnter(event, date);
              },
              onClick: (event) => {
                var _a;
                (_a = dayProps == null ? void 0 : dayProps.onClick) == null ? void 0 : _a.call(dayProps, event);
                __onDayClick == null ? void 0 : __onDayClick(event, date);
              },
              onMouseDown: (event) => {
                var _a;
                (_a = dayProps == null ? void 0 : dayProps.onMouseDown) == null ? void 0 : _a.call(dayProps, event);
                __preventFocus && event.preventDefault();
              },
              tabIndex: __preventFocus || !isDateInTabOrder ? -1 : 0
            }
          )
        },
        date.toString()
      );
    });
    return (0, import_jsx_runtime6.jsxs)("tr", { ...getStyles("monthRow"), children: [
      withWeekNumbers && (0, import_jsx_runtime6.jsx)("td", { ...getStyles("weekNumber"), children: getWeekNumber(row) }),
      cells
    ] }, rowIndex);
  });
  return (0, import_jsx_runtime6.jsxs)(Box, { component: "table", ...getStyles("month"), size, ref, ...others, children: [
    !hideWeekdays && (0, import_jsx_runtime6.jsx)("thead", { ...getStyles("monthThead"), children: (0, import_jsx_runtime6.jsx)(
      WeekdaysRow,
      {
        __staticSelector: __staticSelector || "Month",
        locale,
        firstDayOfWeek,
        weekdayFormat,
        size,
        classNames: resolvedClassNames,
        styles: resolvedStyles,
        unstyled,
        withWeekNumbers
      }
    ) }),
    (0, import_jsx_runtime6.jsx)("tbody", { ...getStyles("monthTbody"), children: rows })
  ] });
});
Month.classes = classes4;
Month.displayName = "@mantine/dates/Month";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/PickerControl/PickerControl.mjs
var import_jsx_runtime7 = __toESM(require_jsx_runtime(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/PickerControl/PickerControl.module.css.mjs
var classes5 = { "pickerControl": "m_dc6a3c71" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/PickerControl/PickerControl.mjs
var defaultProps5 = {};
var varsResolver4 = createVarsResolver((_, { size }) => ({
  pickerControl: {
    "--dpc-fz": getFontSize(size),
    "--dpc-size": getSize(size, "dpc-size")
  }
}));
var PickerControl = factory((_props, ref) => {
  const props = useProps("PickerControl", defaultProps5, _props);
  const {
    classNames,
    className,
    style,
    styles,
    unstyled,
    vars,
    firstInRange,
    lastInRange,
    inRange,
    __staticSelector,
    selected,
    disabled,
    ...others
  } = props;
  const getStyles = useStyles({
    name: __staticSelector || "PickerControl",
    classes: classes5,
    props,
    className,
    style,
    classNames,
    styles,
    unstyled,
    vars,
    varsResolver: varsResolver4,
    rootSelector: "pickerControl"
  });
  return (0, import_jsx_runtime7.jsx)(
    UnstyledButton,
    {
      ...getStyles("pickerControl"),
      ref,
      unstyled,
      "data-picker-control": true,
      "data-selected": selected && !disabled || void 0,
      "data-disabled": disabled || void 0,
      "data-in-range": inRange && !disabled && !selected || void 0,
      "data-first-in-range": firstInRange && !disabled || void 0,
      "data-last-in-range": lastInRange && !disabled || void 0,
      disabled,
      ...others
    }
  );
});
PickerControl.classes = classes5;
PickerControl.displayName = "@mantine/dates/PickerControl";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearsList/YearsList.mjs
var import_jsx_runtime8 = __toESM(require_jsx_runtime(), 1);
var import_dayjs19 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearsList/get-year-in-tab-order/get-year-in-tab-order.mjs
var import_dayjs18 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearsList/is-year-disabled/is-year-disabled.mjs
var import_dayjs17 = __toESM(require_dayjs_min(), 1);
function isYearDisabled(year, minDate, maxDate) {
  if (!minDate && !maxDate) {
    return false;
  }
  if (minDate && (0, import_dayjs17.default)(year).isBefore(minDate, "year")) {
    return true;
  }
  if (maxDate && (0, import_dayjs17.default)(year).isAfter(maxDate, "year")) {
    return true;
  }
  return false;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearsList/get-year-in-tab-order/get-year-in-tab-order.mjs
function getYearInTabOrder(years, minDate, maxDate, getYearControlProps) {
  const enabledYears = years.flat().filter(
    (year) => {
      var _a;
      return !isYearDisabled(year, minDate, maxDate) && !((_a = getYearControlProps == null ? void 0 : getYearControlProps(year)) == null ? void 0 : _a.disabled);
    }
  );
  const selectedYear = enabledYears.find((year) => {
    var _a;
    return (_a = getYearControlProps == null ? void 0 : getYearControlProps(year)) == null ? void 0 : _a.selected;
  });
  if (selectedYear) {
    return selectedYear;
  }
  const currentYear = enabledYears.find((year) => (0, import_dayjs18.default)().isSame(year, "year"));
  if (currentYear) {
    return currentYear;
  }
  return enabledYears[0];
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearsList/get-years-data/get-years-data.mjs
function getYearsData(decade) {
  const year = decade.getFullYear();
  const rounded = year - year % 10;
  let currentYearIndex = 0;
  const results = [[], [], [], []];
  for (let i = 0; i < 4; i += 1) {
    const max = i === 3 ? 1 : 3;
    for (let j = 0; j < max; j += 1) {
      results[i].push(new Date(rounded + currentYearIndex, 0));
      currentYearIndex += 1;
    }
  }
  return results;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearsList/YearsList.module.css.mjs
var classes6 = { "yearsList": "m_9206547b", "yearsListCell": "m_c5a19c7d" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearsList/YearsList.mjs
var defaultProps6 = {
  yearsListFormat: "YYYY",
  withCellSpacing: true
};
var YearsList = factory((_props, ref) => {
  const props = useProps("YearsList", defaultProps6, _props);
  const {
    classNames,
    className,
    style,
    styles,
    unstyled,
    vars,
    decade,
    yearsListFormat,
    locale,
    minDate,
    maxDate,
    getYearControlProps,
    __staticSelector,
    __getControlRef,
    __onControlKeyDown,
    __onControlClick,
    __onControlMouseEnter,
    __preventFocus,
    __stopPropagation,
    withCellSpacing,
    size,
    ...others
  } = props;
  const getStyles = useStyles({
    name: __staticSelector || "YearsList",
    classes: classes6,
    props,
    className,
    style,
    classNames,
    styles,
    unstyled,
    vars,
    rootSelector: "yearsList"
  });
  const ctx = useDatesContext();
  const years = getYearsData(decade);
  const yearInTabOrder = getYearInTabOrder(years, minDate, maxDate, getYearControlProps);
  const rows = years.map((yearsRow, rowIndex) => {
    const cells = yearsRow.map((year, cellIndex) => {
      const controlProps = getYearControlProps == null ? void 0 : getYearControlProps(year);
      const isYearInTabOrder = (0, import_dayjs19.default)(year).isSame(yearInTabOrder, "year");
      return (0, import_jsx_runtime8.jsx)(
        "td",
        {
          ...getStyles("yearsListCell"),
          "data-with-spacing": withCellSpacing || void 0,
          children: (0, import_jsx_runtime8.jsx)(
            PickerControl,
            {
              ...getStyles("yearsListControl"),
              size,
              unstyled,
              "data-mantine-stop-propagation": __stopPropagation || void 0,
              disabled: isYearDisabled(year, minDate, maxDate),
              ref: (node) => __getControlRef == null ? void 0 : __getControlRef(rowIndex, cellIndex, node),
              ...controlProps,
              onKeyDown: (event) => {
                var _a;
                (_a = controlProps == null ? void 0 : controlProps.onKeyDown) == null ? void 0 : _a.call(controlProps, event);
                __onControlKeyDown == null ? void 0 : __onControlKeyDown(event, { rowIndex, cellIndex, date: year });
              },
              onClick: (event) => {
                var _a;
                (_a = controlProps == null ? void 0 : controlProps.onClick) == null ? void 0 : _a.call(controlProps, event);
                __onControlClick == null ? void 0 : __onControlClick(event, year);
              },
              onMouseEnter: (event) => {
                var _a;
                (_a = controlProps == null ? void 0 : controlProps.onMouseEnter) == null ? void 0 : _a.call(controlProps, event);
                __onControlMouseEnter == null ? void 0 : __onControlMouseEnter(event, year);
              },
              onMouseDown: (event) => {
                var _a;
                (_a = controlProps == null ? void 0 : controlProps.onMouseDown) == null ? void 0 : _a.call(controlProps, event);
                __preventFocus && event.preventDefault();
              },
              tabIndex: __preventFocus || !isYearInTabOrder ? -1 : 0,
              children: (0, import_dayjs19.default)(year).locale(ctx.getLocale(locale)).format(yearsListFormat)
            }
          )
        },
        cellIndex
      );
    });
    return (0, import_jsx_runtime8.jsx)("tr", { ...getStyles("yearsListRow"), children: cells }, rowIndex);
  });
  return (0, import_jsx_runtime8.jsx)(Box, { component: "table", ref, size, ...getStyles("yearsList"), ...others, children: (0, import_jsx_runtime8.jsx)("tbody", { children: rows }) });
});
YearsList.classes = classes6;
YearsList.displayName = "@mantine/dates/YearsList";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthsList/MonthsList.mjs
var import_jsx_runtime9 = __toESM(require_jsx_runtime(), 1);
var import_dayjs23 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthsList/get-month-in-tab-order/get-month-in-tab-order.mjs
var import_dayjs21 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthsList/is-month-disabled/is-month-disabled.mjs
var import_dayjs20 = __toESM(require_dayjs_min(), 1);
function isMonthDisabled(month, minDate, maxDate) {
  if (!minDate && !maxDate) {
    return false;
  }
  if (minDate && (0, import_dayjs20.default)(month).isBefore(minDate, "month")) {
    return true;
  }
  if (maxDate && (0, import_dayjs20.default)(month).isAfter(maxDate, "month")) {
    return true;
  }
  return false;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthsList/get-month-in-tab-order/get-month-in-tab-order.mjs
function getMonthInTabOrder(months, minDate, maxDate, getMonthControlProps) {
  const enabledMonths = months.flat().filter(
    (month) => {
      var _a;
      return !isMonthDisabled(month, minDate, maxDate) && !((_a = getMonthControlProps == null ? void 0 : getMonthControlProps(month)) == null ? void 0 : _a.disabled);
    }
  );
  const selectedMonth = enabledMonths.find((month) => {
    var _a;
    return (_a = getMonthControlProps == null ? void 0 : getMonthControlProps(month)) == null ? void 0 : _a.selected;
  });
  if (selectedMonth) {
    return selectedMonth;
  }
  const currentMonth = enabledMonths.find((month) => (0, import_dayjs21.default)().isSame(month, "month"));
  if (currentMonth) {
    return currentMonth;
  }
  return enabledMonths[0];
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthsList/get-months-data/get-months-data.mjs
var import_dayjs22 = __toESM(require_dayjs_min(), 1);
function getMonthsData(year) {
  const startOfYear = (0, import_dayjs22.default)(year).startOf("year").toDate();
  const results = [[], [], [], []];
  let currentMonthIndex = 0;
  for (let i = 0; i < 4; i += 1) {
    for (let j = 0; j < 3; j += 1) {
      results[i].push((0, import_dayjs22.default)(startOfYear).add(currentMonthIndex, "months").toDate());
      currentMonthIndex += 1;
    }
  }
  return results;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthsList/MonthsList.module.css.mjs
var classes7 = { "monthsList": "m_2a6c32d", "monthsListCell": "m_fe27622f" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthsList/MonthsList.mjs
var defaultProps7 = {
  monthsListFormat: "MMM",
  withCellSpacing: true
};
var MonthsList = factory((_props, ref) => {
  const props = useProps("MonthsList", defaultProps7, _props);
  const {
    classNames,
    className,
    style,
    styles,
    unstyled,
    vars,
    __staticSelector,
    year,
    monthsListFormat,
    locale,
    minDate,
    maxDate,
    getMonthControlProps,
    __getControlRef,
    __onControlKeyDown,
    __onControlClick,
    __onControlMouseEnter,
    __preventFocus,
    __stopPropagation,
    withCellSpacing,
    size,
    ...others
  } = props;
  const getStyles = useStyles({
    name: __staticSelector || "MonthsList",
    classes: classes7,
    props,
    className,
    style,
    classNames,
    styles,
    unstyled,
    vars,
    rootSelector: "monthsList"
  });
  const ctx = useDatesContext();
  const months = getMonthsData(year);
  const monthInTabOrder = getMonthInTabOrder(months, minDate, maxDate, getMonthControlProps);
  const rows = months.map((monthsRow, rowIndex) => {
    const cells = monthsRow.map((month, cellIndex) => {
      const controlProps = getMonthControlProps == null ? void 0 : getMonthControlProps(month);
      const isMonthInTabOrder = (0, import_dayjs23.default)(month).isSame(monthInTabOrder, "month");
      return (0, import_jsx_runtime9.jsx)(
        "td",
        {
          ...getStyles("monthsListCell"),
          "data-with-spacing": withCellSpacing || void 0,
          children: (0, import_jsx_runtime9.jsx)(
            PickerControl,
            {
              ...getStyles("monthsListControl"),
              size,
              unstyled,
              __staticSelector: __staticSelector || "MonthsList",
              "data-mantine-stop-propagation": __stopPropagation || void 0,
              disabled: isMonthDisabled(month, minDate, maxDate),
              ref: (node) => __getControlRef == null ? void 0 : __getControlRef(rowIndex, cellIndex, node),
              ...controlProps,
              onKeyDown: (event) => {
                var _a;
                (_a = controlProps == null ? void 0 : controlProps.onKeyDown) == null ? void 0 : _a.call(controlProps, event);
                __onControlKeyDown == null ? void 0 : __onControlKeyDown(event, { rowIndex, cellIndex, date: month });
              },
              onClick: (event) => {
                var _a;
                (_a = controlProps == null ? void 0 : controlProps.onClick) == null ? void 0 : _a.call(controlProps, event);
                __onControlClick == null ? void 0 : __onControlClick(event, month);
              },
              onMouseEnter: (event) => {
                var _a;
                (_a = controlProps == null ? void 0 : controlProps.onMouseEnter) == null ? void 0 : _a.call(controlProps, event);
                __onControlMouseEnter == null ? void 0 : __onControlMouseEnter(event, month);
              },
              onMouseDown: (event) => {
                var _a;
                (_a = controlProps == null ? void 0 : controlProps.onMouseDown) == null ? void 0 : _a.call(controlProps, event);
                __preventFocus && event.preventDefault();
              },
              tabIndex: __preventFocus || !isMonthInTabOrder ? -1 : 0,
              children: (0, import_dayjs23.default)(month).locale(ctx.getLocale(locale)).format(monthsListFormat)
            }
          )
        },
        cellIndex
      );
    });
    return (0, import_jsx_runtime9.jsx)("tr", { ...getStyles("monthsListRow"), children: cells }, rowIndex);
  });
  return (0, import_jsx_runtime9.jsx)(Box, { component: "table", ref, size, ...getStyles("monthsList"), ...others, children: (0, import_jsx_runtime9.jsx)("tbody", { children: rows }) });
});
MonthsList.classes = classes7;
MonthsList.displayName = "@mantine/dates/MonthsList";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/CalendarHeader/CalendarHeader.mjs
var import_jsx_runtime10 = __toESM(require_jsx_runtime(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/CalendarHeader/CalendarHeader.module.css.mjs
var classes8 = { "calendarHeader": "m_730a79ed", "calendarHeaderLevel": "m_f6645d97", "calendarHeaderControl": "m_2351eeb0", "calendarHeaderControlIcon": "m_367dc749" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/CalendarHeader/CalendarHeader.mjs
var defaultProps8 = {
  nextDisabled: false,
  previousDisabled: false,
  hasNextLevel: true,
  withNext: true,
  withPrevious: true
};
var varsResolver5 = createVarsResolver((_, { size }) => ({
  calendarHeader: {
    "--dch-control-size": getSize(size, "dch-control-size"),
    "--dch-fz": getFontSize(size)
  }
}));
var CalendarHeader = factory((_props, ref) => {
  const props = useProps("CalendarHeader", defaultProps8, _props);
  const {
    classNames,
    className,
    style,
    styles,
    unstyled,
    vars,
    nextIcon,
    previousIcon,
    nextLabel,
    previousLabel,
    onNext,
    onPrevious,
    onLevelClick,
    label,
    nextDisabled,
    previousDisabled,
    hasNextLevel,
    levelControlAriaLabel,
    withNext,
    withPrevious,
    __staticSelector,
    __preventFocus,
    __stopPropagation,
    ...others
  } = props;
  const getStyles = useStyles({
    name: __staticSelector || "CalendarHeader",
    classes: classes8,
    props,
    className,
    style,
    classNames,
    styles,
    unstyled,
    vars,
    varsResolver: varsResolver5,
    rootSelector: "calendarHeader"
  });
  const preventFocus = __preventFocus ? (event) => event.preventDefault() : void 0;
  return (0, import_jsx_runtime10.jsxs)(Box, { ...getStyles("calendarHeader"), ref, ...others, children: [
    withPrevious && (0, import_jsx_runtime10.jsx)(
      UnstyledButton,
      {
        ...getStyles("calendarHeaderControl"),
        "data-direction": "previous",
        "aria-label": previousLabel,
        onClick: onPrevious,
        unstyled,
        onMouseDown: preventFocus,
        disabled: previousDisabled,
        "data-disabled": previousDisabled || void 0,
        tabIndex: __preventFocus || previousDisabled ? -1 : 0,
        "data-mantine-stop-propagation": __stopPropagation || void 0,
        children: previousIcon || (0, import_jsx_runtime10.jsx)(
          AccordionChevron,
          {
            ...getStyles("calendarHeaderControlIcon"),
            "data-direction": "previous",
            size: "45%"
          }
        )
      }
    ),
    (0, import_jsx_runtime10.jsx)(
      UnstyledButton,
      {
        component: hasNextLevel ? "button" : "div",
        ...getStyles("calendarHeaderLevel"),
        onClick: hasNextLevel ? onLevelClick : void 0,
        unstyled,
        onMouseDown: hasNextLevel ? preventFocus : void 0,
        disabled: !hasNextLevel,
        "data-static": !hasNextLevel || void 0,
        "aria-label": levelControlAriaLabel,
        tabIndex: __preventFocus || !hasNextLevel ? -1 : 0,
        "data-mantine-stop-propagation": __stopPropagation || void 0,
        children: label
      }
    ),
    withNext && (0, import_jsx_runtime10.jsx)(
      UnstyledButton,
      {
        ...getStyles("calendarHeaderControl"),
        "data-direction": "next",
        "aria-label": nextLabel,
        onClick: onNext,
        unstyled,
        onMouseDown: preventFocus,
        disabled: nextDisabled,
        "data-disabled": nextDisabled || void 0,
        tabIndex: __preventFocus || nextDisabled ? -1 : 0,
        "data-mantine-stop-propagation": __stopPropagation || void 0,
        children: nextIcon || (0, import_jsx_runtime10.jsx)(
          AccordionChevron,
          {
            ...getStyles("calendarHeaderControlIcon"),
            "data-direction": "next",
            size: "45%"
          }
        )
      }
    )
  ] });
});
CalendarHeader.classes = classes8;
CalendarHeader.displayName = "@mantine/dates/CalendarHeader";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DecadeLevel/DecadeLevel.mjs
var import_jsx_runtime11 = __toESM(require_jsx_runtime(), 1);
var import_dayjs24 = __toESM(require_dayjs_min(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DecadeLevel/get-decade-range/get-decade-range.mjs
function getDecadeRange(decade) {
  const years = getYearsData(decade);
  return [years[0][0], years[3][0]];
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DecadeLevel/DecadeLevel.mjs
var defaultProps9 = {
  decadeLabelFormat: "YYYY"
};
var DecadeLevel = factory((_props, ref) => {
  const props = useProps("DecadeLevel", defaultProps9, _props);
  const {
    // YearsList settings
    decade,
    locale,
    minDate,
    maxDate,
    yearsListFormat,
    getYearControlProps,
    __getControlRef,
    __onControlKeyDown,
    __onControlClick,
    __onControlMouseEnter,
    withCellSpacing,
    // CalendarHeader settings
    __preventFocus,
    nextIcon,
    previousIcon,
    nextLabel,
    previousLabel,
    onNext,
    onPrevious,
    nextDisabled,
    previousDisabled,
    levelControlAriaLabel,
    withNext,
    withPrevious,
    // Other props
    decadeLabelFormat,
    classNames,
    styles,
    unstyled,
    __staticSelector,
    __stopPropagation,
    size,
    ...others
  } = props;
  const ctx = useDatesContext();
  const [startOfDecade, endOfDecade] = getDecadeRange(decade);
  const stylesApiProps = {
    __staticSelector: __staticSelector || "DecadeLevel",
    classNames,
    styles,
    unstyled,
    size
  };
  const _nextDisabled = typeof nextDisabled === "boolean" ? nextDisabled : maxDate ? !(0, import_dayjs24.default)(endOfDecade).endOf("year").isBefore(maxDate) : false;
  const _previousDisabled = typeof previousDisabled === "boolean" ? previousDisabled : minDate ? !(0, import_dayjs24.default)(startOfDecade).startOf("year").isAfter(minDate) : false;
  const formatDecade = (date, format) => (0, import_dayjs24.default)(date).locale(locale || ctx.locale).format(format);
  return (0, import_jsx_runtime11.jsxs)(Box, { "data-decade-level": true, size, ref, ...others, children: [
    (0, import_jsx_runtime11.jsx)(
      CalendarHeader,
      {
        label: typeof decadeLabelFormat === "function" ? decadeLabelFormat(startOfDecade, endOfDecade) : `${formatDecade(startOfDecade, decadeLabelFormat)} – ${formatDecade(
          endOfDecade,
          decadeLabelFormat
        )}`,
        __preventFocus,
        __stopPropagation,
        nextIcon,
        previousIcon,
        nextLabel,
        previousLabel,
        onNext,
        onPrevious,
        nextDisabled: _nextDisabled,
        previousDisabled: _previousDisabled,
        hasNextLevel: false,
        levelControlAriaLabel,
        withNext,
        withPrevious,
        ...stylesApiProps
      }
    ),
    (0, import_jsx_runtime11.jsx)(
      YearsList,
      {
        decade,
        locale,
        minDate,
        maxDate,
        yearsListFormat,
        getYearControlProps,
        __getControlRef,
        __onControlKeyDown,
        __onControlClick,
        __onControlMouseEnter,
        __preventFocus,
        __stopPropagation,
        withCellSpacing,
        ...stylesApiProps
      }
    )
  ] });
});
DecadeLevel.classes = { ...YearsList.classes, ...CalendarHeader.classes };
DecadeLevel.displayName = "@mantine/dates/DecadeLevel";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearLevel/YearLevel.mjs
var import_jsx_runtime12 = __toESM(require_jsx_runtime(), 1);
var import_dayjs25 = __toESM(require_dayjs_min(), 1);
var defaultProps10 = {
  yearLabelFormat: "YYYY"
};
var YearLevel = factory((_props, ref) => {
  const props = useProps("YearLevel", defaultProps10, _props);
  const {
    // MonthsList settings
    year,
    locale,
    minDate,
    maxDate,
    monthsListFormat,
    getMonthControlProps,
    __getControlRef,
    __onControlKeyDown,
    __onControlClick,
    __onControlMouseEnter,
    withCellSpacing,
    // CalendarHeader settings
    __preventFocus,
    nextIcon,
    previousIcon,
    nextLabel,
    previousLabel,
    onNext,
    onPrevious,
    onLevelClick,
    nextDisabled,
    previousDisabled,
    hasNextLevel,
    levelControlAriaLabel,
    withNext,
    withPrevious,
    // Other props
    yearLabelFormat,
    __staticSelector,
    __stopPropagation,
    size,
    classNames,
    styles,
    unstyled,
    ...others
  } = props;
  const ctx = useDatesContext();
  const stylesApiProps = {
    __staticSelector: __staticSelector || "YearLevel",
    classNames,
    styles,
    unstyled,
    size
  };
  const _nextDisabled = typeof nextDisabled === "boolean" ? nextDisabled : maxDate ? !(0, import_dayjs25.default)(year).endOf("year").isBefore(maxDate) : false;
  const _previousDisabled = typeof previousDisabled === "boolean" ? previousDisabled : minDate ? !(0, import_dayjs25.default)(year).startOf("year").isAfter(minDate) : false;
  return (0, import_jsx_runtime12.jsxs)(Box, { "data-year-level": true, size, ref, ...others, children: [
    (0, import_jsx_runtime12.jsx)(
      CalendarHeader,
      {
        label: typeof yearLabelFormat === "function" ? yearLabelFormat(year) : (0, import_dayjs25.default)(year).locale(locale || ctx.locale).format(yearLabelFormat),
        __preventFocus,
        __stopPropagation,
        nextIcon,
        previousIcon,
        nextLabel,
        previousLabel,
        onNext,
        onPrevious,
        onLevelClick,
        nextDisabled: _nextDisabled,
        previousDisabled: _previousDisabled,
        hasNextLevel,
        levelControlAriaLabel,
        withNext,
        withPrevious,
        ...stylesApiProps
      }
    ),
    (0, import_jsx_runtime12.jsx)(
      MonthsList,
      {
        year,
        locale,
        minDate,
        maxDate,
        monthsListFormat,
        getMonthControlProps,
        __getControlRef,
        __onControlKeyDown,
        __onControlClick,
        __onControlMouseEnter,
        __preventFocus,
        __stopPropagation,
        withCellSpacing,
        ...stylesApiProps
      }
    )
  ] });
});
YearLevel.classes = { ...CalendarHeader.classes, ...MonthsList.classes };
YearLevel.displayName = "@mantine/dates/YearLevel";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthLevel/MonthLevel.mjs
var import_jsx_runtime13 = __toESM(require_jsx_runtime(), 1);
var import_dayjs26 = __toESM(require_dayjs_min(), 1);
var defaultProps11 = {
  monthLabelFormat: "MMMM YYYY"
};
var MonthLevel = factory((_props, ref) => {
  const props = useProps("MonthLevel", defaultProps11, _props);
  const {
    // Month settings
    month,
    locale,
    firstDayOfWeek,
    weekdayFormat,
    weekendDays,
    getDayProps,
    excludeDate,
    minDate,
    maxDate,
    renderDay,
    hideOutsideDates,
    hideWeekdays,
    getDayAriaLabel,
    __getDayRef,
    __onDayKeyDown,
    __onDayClick,
    __onDayMouseEnter,
    withCellSpacing,
    highlightToday,
    withWeekNumbers,
    // CalendarHeader settings
    __preventFocus,
    __stopPropagation,
    nextIcon,
    previousIcon,
    nextLabel,
    previousLabel,
    onNext,
    onPrevious,
    onLevelClick,
    nextDisabled,
    previousDisabled,
    hasNextLevel,
    levelControlAriaLabel,
    withNext,
    withPrevious,
    // Other props
    monthLabelFormat,
    classNames,
    styles,
    unstyled,
    __staticSelector,
    size,
    static: isStatic,
    ...others
  } = props;
  const ctx = useDatesContext();
  const stylesApiProps = {
    __staticSelector: __staticSelector || "MonthLevel",
    classNames,
    styles,
    unstyled,
    size
  };
  const _nextDisabled = typeof nextDisabled === "boolean" ? nextDisabled : maxDate ? !(0, import_dayjs26.default)(month).endOf("month").isBefore(maxDate) : false;
  const _previousDisabled = typeof previousDisabled === "boolean" ? previousDisabled : minDate ? !(0, import_dayjs26.default)(month).startOf("month").isAfter(minDate) : false;
  return (0, import_jsx_runtime13.jsxs)(Box, { "data-month-level": true, size, ref, ...others, children: [
    (0, import_jsx_runtime13.jsx)(
      CalendarHeader,
      {
        label: typeof monthLabelFormat === "function" ? monthLabelFormat(month) : (0, import_dayjs26.default)(month).locale(locale || ctx.locale).format(monthLabelFormat),
        __preventFocus,
        __stopPropagation,
        nextIcon,
        previousIcon,
        nextLabel,
        previousLabel,
        onNext,
        onPrevious,
        onLevelClick,
        nextDisabled: _nextDisabled,
        previousDisabled: _previousDisabled,
        hasNextLevel,
        levelControlAriaLabel,
        withNext,
        withPrevious,
        ...stylesApiProps
      }
    ),
    (0, import_jsx_runtime13.jsx)(
      Month,
      {
        month,
        locale,
        firstDayOfWeek,
        weekdayFormat,
        weekendDays,
        getDayProps,
        excludeDate,
        minDate,
        maxDate,
        renderDay,
        hideOutsideDates,
        hideWeekdays,
        getDayAriaLabel,
        __getDayRef,
        __onDayKeyDown,
        __onDayClick,
        __onDayMouseEnter,
        __preventFocus,
        __stopPropagation,
        static: isStatic,
        withCellSpacing,
        highlightToday,
        withWeekNumbers,
        ...stylesApiProps
      }
    )
  ] });
});
MonthLevel.classes = { ...Month.classes, ...CalendarHeader.classes };
MonthLevel.displayName = "@mantine/dates/MonthLevel";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/LevelsGroup/LevelsGroup.mjs
var import_jsx_runtime14 = __toESM(require_jsx_runtime(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/LevelsGroup/LevelsGroup.module.css.mjs
var classes9 = { "levelsGroup": "m_30b26e33" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/LevelsGroup/LevelsGroup.mjs
var defaultProps12 = {};
var LevelsGroup = factory((_props, ref) => {
  const props = useProps("LevelsGroup", defaultProps12, _props);
  const { classNames, className, style, styles, unstyled, vars, __staticSelector, ...others } = props;
  const getStyles = useStyles({
    name: __staticSelector || "LevelsGroup",
    classes: classes9,
    props,
    className,
    style,
    classNames,
    styles,
    unstyled,
    vars,
    rootSelector: "levelsGroup"
  });
  return (0, import_jsx_runtime14.jsx)(Box, { ref, ...getStyles("levelsGroup"), ...others });
});
LevelsGroup.classes = classes9;
LevelsGroup.displayName = "@mantine/dates/LevelsGroup";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DecadeLevelGroup/DecadeLevelGroup.mjs
var import_jsx_runtime15 = __toESM(require_jsx_runtime(), 1);
var import_dayjs27 = __toESM(require_dayjs_min(), 1);
var import_react3 = __toESM(require_react(), 1);
var defaultProps13 = {
  numberOfColumns: 1
};
var DecadeLevelGroup = factory((_props, ref) => {
  const props = useProps("DecadeLevelGroup", defaultProps13, _props);
  const {
    // DecadeLevel settings
    decade,
    locale,
    minDate,
    maxDate,
    yearsListFormat,
    getYearControlProps,
    __onControlClick,
    __onControlMouseEnter,
    withCellSpacing,
    // CalendarHeader settings
    __preventFocus,
    nextIcon,
    previousIcon,
    nextLabel,
    previousLabel,
    onNext,
    onPrevious,
    nextDisabled,
    previousDisabled,
    // Other settings
    classNames,
    styles,
    unstyled,
    __staticSelector,
    __stopPropagation,
    numberOfColumns,
    levelControlAriaLabel,
    decadeLabelFormat,
    size,
    vars,
    ...others
  } = props;
  const controlsRef = (0, import_react3.useRef)([]);
  const decades = Array(numberOfColumns).fill(0).map((_, decadeIndex) => {
    const currentDecade = (0, import_dayjs27.default)(decade).add(decadeIndex * 10, "years").toDate();
    return (0, import_jsx_runtime15.jsx)(
      DecadeLevel,
      {
        size,
        yearsListFormat,
        decade: currentDecade,
        withNext: decadeIndex === numberOfColumns - 1,
        withPrevious: decadeIndex === 0,
        decadeLabelFormat,
        __onControlClick,
        __onControlMouseEnter,
        __onControlKeyDown: (event, payload) => handleControlKeyDown({
          levelIndex: decadeIndex,
          rowIndex: payload.rowIndex,
          cellIndex: payload.cellIndex,
          event,
          controlsRef
        }),
        __getControlRef: (rowIndex, cellIndex, node) => {
          if (!Array.isArray(controlsRef.current[decadeIndex])) {
            controlsRef.current[decadeIndex] = [];
          }
          if (!Array.isArray(controlsRef.current[decadeIndex][rowIndex])) {
            controlsRef.current[decadeIndex][rowIndex] = [];
          }
          controlsRef.current[decadeIndex][rowIndex][cellIndex] = node;
        },
        levelControlAriaLabel: typeof levelControlAriaLabel === "function" ? levelControlAriaLabel(currentDecade) : levelControlAriaLabel,
        locale,
        minDate,
        maxDate,
        __preventFocus,
        __stopPropagation,
        nextIcon,
        previousIcon,
        nextLabel,
        previousLabel,
        onNext,
        onPrevious,
        nextDisabled,
        previousDisabled,
        getYearControlProps,
        __staticSelector: __staticSelector || "DecadeLevelGroup",
        classNames,
        styles,
        unstyled,
        withCellSpacing
      },
      decadeIndex
    );
  });
  return (0, import_jsx_runtime15.jsx)(
    LevelsGroup,
    {
      classNames,
      styles,
      __staticSelector: __staticSelector || "DecadeLevelGroup",
      ref,
      size,
      unstyled,
      ...others,
      children: decades
    }
  );
});
DecadeLevelGroup.classes = { ...LevelsGroup.classes, ...DecadeLevel.classes };
DecadeLevelGroup.displayName = "@mantine/dates/DecadeLevelGroup";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearLevelGroup/YearLevelGroup.mjs
var import_jsx_runtime16 = __toESM(require_jsx_runtime(), 1);
var import_dayjs28 = __toESM(require_dayjs_min(), 1);
var import_react4 = __toESM(require_react(), 1);
var defaultProps14 = {
  numberOfColumns: 1
};
var YearLevelGroup = factory((_props, ref) => {
  const props = useProps("YearLevelGroup", defaultProps14, _props);
  const {
    // YearLevel settings
    year,
    locale,
    minDate,
    maxDate,
    monthsListFormat,
    getMonthControlProps,
    __onControlClick,
    __onControlMouseEnter,
    withCellSpacing,
    // CalendarHeader settings
    __preventFocus,
    nextIcon,
    previousIcon,
    nextLabel,
    previousLabel,
    onNext,
    onPrevious,
    onLevelClick,
    nextDisabled,
    previousDisabled,
    hasNextLevel,
    // Other settings
    classNames,
    styles,
    unstyled,
    __staticSelector,
    __stopPropagation,
    numberOfColumns,
    levelControlAriaLabel,
    yearLabelFormat,
    size,
    vars,
    ...others
  } = props;
  const controlsRef = (0, import_react4.useRef)([]);
  const years = Array(numberOfColumns).fill(0).map((_, yearIndex) => {
    const currentYear = (0, import_dayjs28.default)(year).add(yearIndex, "years").toDate();
    return (0, import_jsx_runtime16.jsx)(
      YearLevel,
      {
        size,
        monthsListFormat,
        year: currentYear,
        withNext: yearIndex === numberOfColumns - 1,
        withPrevious: yearIndex === 0,
        yearLabelFormat,
        __stopPropagation,
        __onControlClick,
        __onControlMouseEnter,
        __onControlKeyDown: (event, payload) => handleControlKeyDown({
          levelIndex: yearIndex,
          rowIndex: payload.rowIndex,
          cellIndex: payload.cellIndex,
          event,
          controlsRef
        }),
        __getControlRef: (rowIndex, cellIndex, node) => {
          if (!Array.isArray(controlsRef.current[yearIndex])) {
            controlsRef.current[yearIndex] = [];
          }
          if (!Array.isArray(controlsRef.current[yearIndex][rowIndex])) {
            controlsRef.current[yearIndex][rowIndex] = [];
          }
          controlsRef.current[yearIndex][rowIndex][cellIndex] = node;
        },
        levelControlAriaLabel: typeof levelControlAriaLabel === "function" ? levelControlAriaLabel(currentYear) : levelControlAriaLabel,
        locale,
        minDate,
        maxDate,
        __preventFocus,
        nextIcon,
        previousIcon,
        nextLabel,
        previousLabel,
        onNext,
        onPrevious,
        onLevelClick,
        nextDisabled,
        previousDisabled,
        hasNextLevel,
        getMonthControlProps,
        classNames,
        styles,
        unstyled,
        __staticSelector: __staticSelector || "YearLevelGroup",
        withCellSpacing
      },
      yearIndex
    );
  });
  return (0, import_jsx_runtime16.jsx)(
    LevelsGroup,
    {
      classNames,
      styles,
      __staticSelector: __staticSelector || "YearLevelGroup",
      ref,
      size,
      unstyled,
      ...others,
      children: years
    }
  );
});
YearLevelGroup.classes = { ...YearLevel.classes, ...LevelsGroup.classes };
YearLevelGroup.displayName = "@mantine/dates/YearLevelGroup";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthLevelGroup/MonthLevelGroup.mjs
var import_jsx_runtime17 = __toESM(require_jsx_runtime(), 1);
var import_dayjs29 = __toESM(require_dayjs_min(), 1);
var import_react5 = __toESM(require_react(), 1);
var defaultProps15 = {
  numberOfColumns: 1
};
var MonthLevelGroup = factory((_props, ref) => {
  const props = useProps("MonthLevelGroup", defaultProps15, _props);
  const {
    // Month settings
    month,
    locale,
    firstDayOfWeek,
    weekdayFormat,
    weekendDays,
    getDayProps,
    excludeDate,
    minDate,
    maxDate,
    renderDay,
    hideOutsideDates,
    hideWeekdays,
    getDayAriaLabel,
    __onDayClick,
    __onDayMouseEnter,
    withCellSpacing,
    highlightToday,
    withWeekNumbers,
    // CalendarHeader settings
    __preventFocus,
    nextIcon,
    previousIcon,
    nextLabel,
    previousLabel,
    onNext,
    onPrevious,
    onLevelClick,
    nextDisabled,
    previousDisabled,
    hasNextLevel,
    // Other settings
    classNames,
    styles,
    unstyled,
    numberOfColumns,
    levelControlAriaLabel,
    monthLabelFormat,
    __staticSelector,
    __stopPropagation,
    size,
    static: isStatic,
    vars,
    ...others
  } = props;
  const daysRefs = (0, import_react5.useRef)([]);
  const months = Array(numberOfColumns).fill(0).map((_, monthIndex) => {
    const currentMonth = (0, import_dayjs29.default)(month).add(monthIndex, "months").toDate();
    return (0, import_jsx_runtime17.jsx)(
      MonthLevel,
      {
        month: currentMonth,
        withNext: monthIndex === numberOfColumns - 1,
        withPrevious: monthIndex === 0,
        monthLabelFormat,
        __stopPropagation,
        __onDayClick,
        __onDayMouseEnter,
        __onDayKeyDown: (event, payload) => handleControlKeyDown({
          levelIndex: monthIndex,
          rowIndex: payload.rowIndex,
          cellIndex: payload.cellIndex,
          event,
          controlsRef: daysRefs
        }),
        __getDayRef: (rowIndex, cellIndex, node) => {
          if (!Array.isArray(daysRefs.current[monthIndex])) {
            daysRefs.current[monthIndex] = [];
          }
          if (!Array.isArray(daysRefs.current[monthIndex][rowIndex])) {
            daysRefs.current[monthIndex][rowIndex] = [];
          }
          daysRefs.current[monthIndex][rowIndex][cellIndex] = node;
        },
        levelControlAriaLabel: typeof levelControlAriaLabel === "function" ? levelControlAriaLabel(currentMonth) : levelControlAriaLabel,
        locale,
        firstDayOfWeek,
        weekdayFormat,
        weekendDays,
        getDayProps,
        excludeDate,
        minDate,
        maxDate,
        renderDay,
        hideOutsideDates,
        hideWeekdays,
        getDayAriaLabel,
        __preventFocus,
        nextIcon,
        previousIcon,
        nextLabel,
        previousLabel,
        onNext,
        onPrevious,
        onLevelClick,
        nextDisabled,
        previousDisabled,
        hasNextLevel,
        classNames,
        styles,
        unstyled,
        __staticSelector: __staticSelector || "MonthLevelGroup",
        size,
        static: isStatic,
        withCellSpacing,
        highlightToday,
        withWeekNumbers
      },
      monthIndex
    );
  });
  return (0, import_jsx_runtime17.jsx)(
    LevelsGroup,
    {
      classNames,
      styles,
      __staticSelector: __staticSelector || "MonthLevelGroup",
      ref,
      size,
      ...others,
      children: months
    }
  );
});
MonthLevelGroup.classes = { ...LevelsGroup.classes, ...MonthLevel.classes };
MonthLevelGroup.displayName = "@mantine/dates/MonthLevelGroup";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/PickerInputBase/PickerInputBase.mjs
var import_jsx_runtime18 = __toESM(require_jsx_runtime(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/PickerInputBase/PickerInputBase.module.css.mjs
var classes10 = { "input": "m_6fa5e2aa" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/PickerInputBase/PickerInputBase.mjs
var defaultProps16 = {};
var PickerInputBase = factory((_props, ref) => {
  const {
    inputProps,
    wrapperProps,
    placeholder,
    classNames,
    styles,
    unstyled,
    popoverProps,
    modalProps,
    dropdownType,
    children,
    formattedValue,
    dropdownHandlers,
    dropdownOpened,
    onClick,
    clearable,
    onClear,
    clearButtonProps,
    rightSection,
    shouldClear,
    readOnly,
    disabled,
    value,
    name,
    form,
    type,
    ...others
  } = useInputProps("PickerInputBase", defaultProps16, _props);
  const clearButton = (0, import_jsx_runtime18.jsx)(Input.ClearButton, { onClick: onClear, unstyled, ...clearButtonProps });
  const handleClose = () => {
    const isInvalidRangeValue = type === "range" && Array.isArray(value) && value[0] && !value[1];
    if (isInvalidRangeValue) {
      onClear();
    }
    dropdownHandlers.close();
  };
  return (0, import_jsx_runtime18.jsxs)(import_jsx_runtime18.Fragment, { children: [
    dropdownType === "modal" && !readOnly && (0, import_jsx_runtime18.jsx)(
      Modal,
      {
        opened: dropdownOpened,
        onClose: handleClose,
        withCloseButton: false,
        size: "auto",
        "data-dates-modal": true,
        unstyled,
        ...modalProps,
        children
      }
    ),
    (0, import_jsx_runtime18.jsx)(Input.Wrapper, { ...wrapperProps, children: (0, import_jsx_runtime18.jsxs)(
      Popover,
      {
        position: "bottom-start",
        opened: dropdownOpened,
        trapFocus: true,
        returnFocus: false,
        unstyled,
        ...popoverProps,
        disabled: (popoverProps == null ? void 0 : popoverProps.disabled) || dropdownType === "modal" || readOnly,
        onChange: (_opened) => {
          var _a;
          if (!_opened) {
            (_a = popoverProps == null ? void 0 : popoverProps.onClose) == null ? void 0 : _a.call(popoverProps);
            handleClose();
          }
        },
        children: [
          (0, import_jsx_runtime18.jsx)(Popover.Target, { children: (0, import_jsx_runtime18.jsx)(
            Input,
            {
              "data-dates-input": true,
              "data-read-only": readOnly || void 0,
              disabled,
              component: "button",
              type: "button",
              multiline: true,
              onClick: (event) => {
                onClick == null ? void 0 : onClick(event);
                dropdownHandlers.toggle();
              },
              __clearSection: clearButton,
              __clearable: clearable && shouldClear && !readOnly && !disabled,
              rightSection,
              ...inputProps,
              ref,
              classNames: { ...classNames, input: clsx_default(classes10.input, classNames == null ? void 0 : classNames.input) },
              ...others,
              children: formattedValue || (0, import_jsx_runtime18.jsx)(
                Input.Placeholder,
                {
                  error: inputProps.error,
                  unstyled,
                  className: classNames == null ? void 0 : classNames.placeholder,
                  style: styles == null ? void 0 : styles.placeholder,
                  children: placeholder
                }
              )
            }
          ) }),
          (0, import_jsx_runtime18.jsx)(Popover.Dropdown, { "data-dates-dropdown": true, children })
        ]
      }
    ) }),
    (0, import_jsx_runtime18.jsx)(HiddenDatesInput, { value, name, form, type })
  ] });
});
PickerInputBase.classes = classes10;
PickerInputBase.displayName = "@mantine/dates/PickerInputBase";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Calendar/Calendar.mjs
var import_jsx_runtime19 = __toESM(require_jsx_runtime(), 1);
var import_dayjs31 = __toESM(require_dayjs_min(), 1);
var import_react7 = __toESM(require_react(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/hooks/use-uncontrolled-dates/use-uncontrolled-dates.mjs
var import_react6 = __toESM(require_react(), 1);
var import_dayjs30 = __toESM(require_dayjs_min(), 1);
var getEmptyValue = (type) => type === "range" ? [null, null] : type === "multiple" ? [] : null;
function useUncontrolledDates({
  type,
  value,
  defaultValue,
  onChange,
  applyTimezone = true
}) {
  const storedType = (0, import_react6.useRef)(type);
  const ctx = useDatesContext();
  const [_value, _setValue, controlled] = useUncontrolled({
    value: shiftTimezone("add", value, ctx.getTimezone(), !applyTimezone),
    defaultValue: shiftTimezone("add", defaultValue, ctx.getTimezone(), !applyTimezone),
    finalValue: getEmptyValue(type),
    onChange: (newDate) => {
      onChange == null ? void 0 : onChange(shiftTimezone("remove", newDate, ctx.getTimezone(), !applyTimezone));
    }
  });
  let _finalValue = _value;
  if (storedType.current !== type) {
    storedType.current = type;
    if (value === void 0) {
      _finalValue = defaultValue !== void 0 ? defaultValue : getEmptyValue(type);
      _setValue(_finalValue);
    } else if (true) {
      switch (type) {
        case "default":
          if (value !== null && typeof value !== "string") {
            console.error(
              "[@mantine/dates/use-uncontrolled-dates] Value must be type of `null` or `string`"
            );
          }
          break;
        case "multiple":
          if (!(value instanceof Array)) {
            console.error(
              "[@mantine/dates/use-uncontrolled-dates] Value must be type of `string[]`"
            );
          }
          break;
        case "range":
          if (!(value instanceof Array) || value.length !== 2) {
            console.error(
              "[@mantine/dates/use-uncontrolled-dates] Value must be type of `[string, string]`"
            );
          }
          break;
      }
    }
  }
  return [_finalValue, _setValue, controlled];
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Calendar/clamp-level/clamp-level.mjs
function levelToNumber(level, fallback) {
  if (!level) {
    return fallback || 0;
  }
  return level === "month" ? 0 : level === "year" ? 1 : 2;
}
function levelNumberToLevel(levelNumber) {
  return levelNumber === 0 ? "month" : levelNumber === 1 ? "year" : "decade";
}
function clampLevel(level, minLevel, maxLevel) {
  return levelNumberToLevel(
    clamp(
      levelToNumber(level, 0),
      levelToNumber(minLevel, 0),
      levelToNumber(maxLevel, 2)
    )
  );
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Calendar/Calendar.mjs
var defaultProps17 = {
  maxLevel: "decade",
  minLevel: "month",
  __updateDateOnYearSelect: true,
  __updateDateOnMonthSelect: true
};
var Calendar = factory((_props, ref) => {
  const props = useProps("Calendar", defaultProps17, _props);
  const {
    vars,
    // CalendarLevel props
    maxLevel,
    minLevel,
    defaultLevel,
    level,
    onLevelChange,
    date,
    defaultDate,
    onDateChange,
    numberOfColumns,
    columnsToScroll,
    ariaLabels,
    nextLabel,
    previousLabel,
    onYearSelect,
    onMonthSelect,
    onYearMouseEnter,
    onMonthMouseEnter,
    __updateDateOnYearSelect,
    __updateDateOnMonthSelect,
    // MonthLevelGroup props
    firstDayOfWeek,
    weekdayFormat,
    weekendDays,
    getDayProps,
    excludeDate,
    renderDay,
    hideOutsideDates,
    hideWeekdays,
    getDayAriaLabel,
    monthLabelFormat,
    nextIcon,
    previousIcon,
    __onDayClick,
    __onDayMouseEnter,
    withCellSpacing,
    highlightToday,
    withWeekNumbers,
    // YearLevelGroup props
    monthsListFormat,
    getMonthControlProps,
    yearLabelFormat,
    // DecadeLevelGroup props
    yearsListFormat,
    getYearControlProps,
    decadeLabelFormat,
    // Other props
    classNames,
    styles,
    unstyled,
    minDate,
    maxDate,
    locale,
    __staticSelector,
    size,
    __preventFocus,
    __stopPropagation,
    onNextDecade,
    onPreviousDecade,
    onNextYear,
    onPreviousYear,
    onNextMonth,
    onPreviousMonth,
    static: isStatic,
    __timezoneApplied,
    ...others
  } = props;
  const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
    classNames,
    styles,
    props
  });
  const [_level, setLevel] = useUncontrolled({
    value: level ? clampLevel(level, minLevel, maxLevel) : void 0,
    defaultValue: defaultLevel ? clampLevel(defaultLevel, minLevel, maxLevel) : void 0,
    finalValue: clampLevel(void 0, minLevel, maxLevel),
    onChange: onLevelChange
  });
  const [_date, setDate] = useUncontrolledDates({
    type: "default",
    value: date,
    defaultValue: defaultDate,
    onChange: onDateChange,
    applyTimezone: !__timezoneApplied
  });
  const stylesApiProps = {
    __staticSelector: __staticSelector || "Calendar",
    styles: resolvedStyles,
    classNames: resolvedClassNames,
    unstyled,
    size
  };
  const ctx = useDatesContext();
  const _columnsToScroll = columnsToScroll || numberOfColumns || 1;
  const now = /* @__PURE__ */ new Date();
  const fallbackDate = minDate && minDate > now ? minDate : now;
  const currentDate = _date || shiftTimezone("add", fallbackDate, ctx.getTimezone());
  const handleNextMonth = () => {
    const nextDate = (0, import_dayjs31.default)(currentDate).add(_columnsToScroll, "month").toDate();
    onNextMonth == null ? void 0 : onNextMonth(nextDate);
    setDate(nextDate);
  };
  const handlePreviousMonth = () => {
    const nextDate = (0, import_dayjs31.default)(currentDate).subtract(_columnsToScroll, "month").toDate();
    onPreviousMonth == null ? void 0 : onPreviousMonth(nextDate);
    setDate(nextDate);
  };
  const handleNextYear = () => {
    const nextDate = (0, import_dayjs31.default)(currentDate).add(_columnsToScroll, "year").toDate();
    onNextYear == null ? void 0 : onNextYear(nextDate);
    setDate(nextDate);
  };
  const handlePreviousYear = () => {
    const nextDate = (0, import_dayjs31.default)(currentDate).subtract(_columnsToScroll, "year").toDate();
    onPreviousYear == null ? void 0 : onPreviousYear(nextDate);
    setDate(nextDate);
  };
  const handleNextDecade = () => {
    const nextDate = (0, import_dayjs31.default)(currentDate).add(10 * _columnsToScroll, "year").toDate();
    onNextDecade == null ? void 0 : onNextDecade(nextDate);
    setDate(nextDate);
  };
  const handlePreviousDecade = () => {
    const nextDate = (0, import_dayjs31.default)(currentDate).subtract(10 * _columnsToScroll, "year").toDate();
    onPreviousDecade == null ? void 0 : onPreviousDecade(nextDate);
    setDate(nextDate);
  };
  return (0, import_jsx_runtime19.jsxs)(Box, { ref, size, "data-calendar": true, ...others, children: [
    _level === "month" && (0, import_jsx_runtime19.jsx)(
      MonthLevelGroup,
      {
        month: currentDate,
        minDate,
        maxDate,
        firstDayOfWeek,
        weekdayFormat,
        weekendDays,
        getDayProps,
        excludeDate,
        renderDay,
        hideOutsideDates,
        hideWeekdays,
        getDayAriaLabel,
        onNext: handleNextMonth,
        onPrevious: handlePreviousMonth,
        hasNextLevel: maxLevel !== "month",
        onLevelClick: () => setLevel("year"),
        numberOfColumns,
        locale,
        levelControlAriaLabel: ariaLabels == null ? void 0 : ariaLabels.monthLevelControl,
        nextLabel: (ariaLabels == null ? void 0 : ariaLabels.nextMonth) ?? nextLabel,
        nextIcon,
        previousLabel: (ariaLabels == null ? void 0 : ariaLabels.previousMonth) ?? previousLabel,
        previousIcon,
        monthLabelFormat,
        __onDayClick,
        __onDayMouseEnter,
        __preventFocus,
        __stopPropagation,
        static: isStatic,
        withCellSpacing,
        highlightToday,
        withWeekNumbers,
        ...stylesApiProps
      }
    ),
    _level === "year" && (0, import_jsx_runtime19.jsx)(
      YearLevelGroup,
      {
        year: currentDate,
        numberOfColumns,
        minDate,
        maxDate,
        monthsListFormat,
        getMonthControlProps,
        locale,
        onNext: handleNextYear,
        onPrevious: handlePreviousYear,
        hasNextLevel: maxLevel !== "month" && maxLevel !== "year",
        onLevelClick: () => setLevel("decade"),
        levelControlAriaLabel: ariaLabels == null ? void 0 : ariaLabels.yearLevelControl,
        nextLabel: (ariaLabels == null ? void 0 : ariaLabels.nextYear) ?? nextLabel,
        nextIcon,
        previousLabel: (ariaLabels == null ? void 0 : ariaLabels.previousYear) ?? previousLabel,
        previousIcon,
        yearLabelFormat,
        __onControlMouseEnter: onMonthMouseEnter,
        __onControlClick: (_event, payload) => {
          __updateDateOnMonthSelect && setDate(payload);
          setLevel(clampLevel("month", minLevel, maxLevel));
          onMonthSelect == null ? void 0 : onMonthSelect(payload);
        },
        __preventFocus,
        __stopPropagation,
        withCellSpacing,
        ...stylesApiProps
      }
    ),
    _level === "decade" && (0, import_jsx_runtime19.jsx)(
      DecadeLevelGroup,
      {
        decade: currentDate,
        minDate,
        maxDate,
        yearsListFormat,
        getYearControlProps,
        locale,
        onNext: handleNextDecade,
        onPrevious: handlePreviousDecade,
        numberOfColumns,
        nextLabel: (ariaLabels == null ? void 0 : ariaLabels.nextDecade) ?? nextLabel,
        nextIcon,
        previousLabel: (ariaLabels == null ? void 0 : ariaLabels.previousDecade) ?? previousLabel,
        previousIcon,
        decadeLabelFormat,
        __onControlMouseEnter: onYearMouseEnter,
        __onControlClick: (_event, payload) => {
          __updateDateOnYearSelect && setDate(payload);
          setLevel(clampLevel("year", minLevel, maxLevel));
          onYearSelect == null ? void 0 : onYearSelect(payload);
        },
        __preventFocus,
        __stopPropagation,
        withCellSpacing,
        ...stylesApiProps
      }
    )
  ] });
});
Calendar.classes = {
  ...DecadeLevelGroup.classes,
  ...YearLevelGroup.classes,
  ...MonthLevelGroup.classes
};
Calendar.displayName = "@mantine/dates/Calendar";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/Calendar/pick-calendar-levels-props/pick-calendar-levels-props.mjs
function pickCalendarProps(props) {
  const {
    maxLevel,
    minLevel,
    defaultLevel,
    level,
    onLevelChange,
    nextIcon,
    previousIcon,
    date,
    defaultDate,
    onDateChange,
    numberOfColumns,
    columnsToScroll,
    ariaLabels,
    nextLabel,
    previousLabel,
    onYearSelect,
    onMonthSelect,
    onYearMouseEnter,
    onMonthMouseEnter,
    onNextMonth,
    onPreviousMonth,
    onNextYear,
    onPreviousYear,
    onNextDecade,
    onPreviousDecade,
    withCellSpacing,
    highlightToday,
    __updateDateOnYearSelect,
    __updateDateOnMonthSelect,
    withWeekNumbers,
    // MonthLevelGroup props
    firstDayOfWeek,
    weekdayFormat,
    weekendDays,
    getDayProps,
    excludeDate,
    renderDay,
    hideOutsideDates,
    hideWeekdays,
    getDayAriaLabel,
    monthLabelFormat,
    // YearLevelGroup props
    monthsListFormat,
    getMonthControlProps,
    yearLabelFormat,
    // DecadeLevelGroup props
    yearsListFormat,
    getYearControlProps,
    decadeLabelFormat,
    // External picker props
    allowSingleDateInRange,
    allowDeselect,
    // Other props
    minDate,
    maxDate,
    locale,
    ...others
  } = props;
  return {
    calendarProps: {
      maxLevel,
      minLevel,
      defaultLevel,
      level,
      onLevelChange,
      nextIcon,
      previousIcon,
      date,
      defaultDate,
      onDateChange,
      numberOfColumns,
      columnsToScroll,
      ariaLabels,
      nextLabel,
      previousLabel,
      onYearSelect,
      onMonthSelect,
      onYearMouseEnter,
      onMonthMouseEnter,
      onNextMonth,
      onPreviousMonth,
      onNextYear,
      onPreviousYear,
      onNextDecade,
      onPreviousDecade,
      withCellSpacing,
      highlightToday,
      __updateDateOnYearSelect,
      __updateDateOnMonthSelect,
      withWeekNumbers,
      // MonthLevelGroup props
      firstDayOfWeek,
      weekdayFormat,
      weekendDays,
      getDayProps,
      excludeDate,
      renderDay,
      hideOutsideDates,
      hideWeekdays,
      getDayAriaLabel,
      monthLabelFormat,
      // YearLevelGroup props
      monthsListFormat,
      getMonthControlProps,
      yearLabelFormat,
      // DecadeLevelGroup props
      yearsListFormat,
      getYearControlProps,
      decadeLabelFormat,
      // External picker props
      allowSingleDateInRange,
      allowDeselect,
      // Other props
      minDate,
      maxDate,
      locale
    },
    others
  };
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearPicker/YearPicker.mjs
var import_jsx_runtime20 = __toESM(require_jsx_runtime(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/hooks/use-dates-state/use-dates-state.mjs
var import_dayjs33 = __toESM(require_dayjs_min(), 1);
var import_react8 = __toESM(require_react(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/hooks/use-dates-state/is-in-range/is-in-range.mjs
var import_dayjs32 = __toESM(require_dayjs_min(), 1);
function isInRange(date, range) {
  const _range = [...range].sort((a, b) => a.getTime() - b.getTime());
  return (0, import_dayjs32.default)(_range[0]).startOf("day").subtract(1, "ms").isBefore(date) && (0, import_dayjs32.default)(_range[1]).endOf("day").add(1, "ms").isAfter(date);
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/hooks/use-dates-state/use-dates-state.mjs
function useDatesState({
  type,
  level,
  value,
  defaultValue,
  onChange,
  allowSingleDateInRange,
  allowDeselect,
  onMouseLeave,
  applyTimezone = true
}) {
  const [_value, setValue] = useUncontrolledDates({
    type,
    value,
    defaultValue,
    onChange,
    applyTimezone
  });
  const [pickedDate, setPickedDate] = (0, import_react8.useState)(
    type === "range" ? _value[0] && !_value[1] ? _value[0] : null : null
  );
  const [hoveredDate, setHoveredDate] = (0, import_react8.useState)(null);
  const onDateChange = (date) => {
    if (type === "range") {
      if (pickedDate instanceof Date && !_value[1]) {
        if ((0, import_dayjs33.default)(date).isSame(pickedDate, level) && !allowSingleDateInRange) {
          setPickedDate(null);
          setHoveredDate(null);
          setValue([null, null]);
          return;
        }
        const result = [date, pickedDate];
        result.sort((a, b) => a.getTime() - b.getTime());
        setValue(result);
        setHoveredDate(null);
        setPickedDate(null);
        return;
      }
      if (_value[0] && !_value[1] && (0, import_dayjs33.default)(date).isSame(_value[0], level) && !allowSingleDateInRange) {
        setPickedDate(null);
        setHoveredDate(null);
        setValue([null, null]);
        return;
      }
      setValue([date, null]);
      setHoveredDate(null);
      setPickedDate(date);
      return;
    }
    if (type === "multiple") {
      if (_value.some((selected) => (0, import_dayjs33.default)(selected).isSame(date, level))) {
        setValue(_value.filter((selected) => !(0, import_dayjs33.default)(selected).isSame(date, level)));
      } else {
        setValue([..._value, date]);
      }
      return;
    }
    if (_value && allowDeselect && (0, import_dayjs33.default)(date).isSame(_value, level)) {
      setValue(null);
    } else {
      setValue(date);
    }
  };
  const isDateInRange = (date) => {
    if (pickedDate instanceof Date && hoveredDate instanceof Date) {
      return isInRange(date, [hoveredDate, pickedDate]);
    }
    if (_value[0] instanceof Date && _value[1] instanceof Date) {
      return isInRange(date, _value);
    }
    return false;
  };
  const onRootMouseLeave = type === "range" ? (event) => {
    onMouseLeave == null ? void 0 : onMouseLeave(event);
    setHoveredDate(null);
  } : onMouseLeave;
  const isFirstInRange = (date) => {
    if (!(_value[0] instanceof Date)) {
      return false;
    }
    if ((0, import_dayjs33.default)(date).isSame(_value[0], level)) {
      return !(hoveredDate && (0, import_dayjs33.default)(hoveredDate).isBefore(_value[0]));
    }
    return false;
  };
  const isLastInRange = (date) => {
    if (_value[1] instanceof Date) {
      return (0, import_dayjs33.default)(date).isSame(_value[1], level);
    }
    if (!(_value[0] instanceof Date) || !hoveredDate) {
      return false;
    }
    return (0, import_dayjs33.default)(hoveredDate).isBefore(_value[0]) && (0, import_dayjs33.default)(date).isSame(_value[0], level);
  };
  const getControlProps = (date) => {
    if (type === "range") {
      return {
        selected: _value.some(
          (selection) => selection && (0, import_dayjs33.default)(selection).isSame(date, level)
        ),
        inRange: isDateInRange(date),
        firstInRange: isFirstInRange(date),
        lastInRange: isLastInRange(date),
        "data-autofocus": !!_value[0] && (0, import_dayjs33.default)(_value[0]).isSame(date, level) || void 0
      };
    }
    if (type === "multiple") {
      return {
        selected: _value.some(
          (selection) => selection && (0, import_dayjs33.default)(selection).isSame(date, level)
        ),
        "data-autofocus": !!_value[0] && (0, import_dayjs33.default)(_value[0]).isSame(date, level) || void 0
      };
    }
    const selected = (0, import_dayjs33.default)(_value).isSame(date, level);
    return { selected, "data-autofocus": selected || void 0 };
  };
  const onHoveredDateChange = type === "range" && pickedDate ? setHoveredDate : () => {
  };
  (0, import_react8.useEffect)(() => {
    if (type !== "range") {
      return;
    }
    if (_value[0] && !_value[1] && (pickedDate == null ? void 0 : pickedDate.getTime()) !== _value[0].getTime()) {
      setPickedDate(_value[0]);
    } else {
      const isNeitherSelected = _value[0] == null && _value[1] == null;
      const isBothSelected = _value[0] != null && _value[1] != null;
      if (isNeitherSelected || isBothSelected) {
        setPickedDate(null);
        setHoveredDate(null);
      }
    }
  }, [_value]);
  return {
    onDateChange,
    onRootMouseLeave,
    onHoveredDateChange,
    getControlProps,
    _value,
    setValue
  };
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearPicker/YearPicker.mjs
var import_dayjs34 = __toESM(require_dayjs_min(), 1);
var import_react9 = __toESM(require_react(), 1);
var defaultProps18 = {
  type: "default"
};
var YearPicker = factory((_props, ref) => {
  const props = useProps("YearPicker", defaultProps18, _props);
  const {
    classNames,
    styles,
    vars,
    type,
    defaultValue,
    value,
    onChange,
    __staticSelector,
    getYearControlProps,
    allowSingleDateInRange,
    allowDeselect,
    onMouseLeave,
    onYearSelect,
    __updateDateOnYearSelect,
    __timezoneApplied,
    ...others
  } = props;
  const { onDateChange, onRootMouseLeave, onHoveredDateChange, getControlProps } = useDatesState({
    type,
    level: "year",
    allowDeselect,
    allowSingleDateInRange,
    value,
    defaultValue,
    onChange,
    onMouseLeave,
    applyTimezone: !__timezoneApplied
  });
  const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
    classNames,
    styles,
    props
  });
  const ctx = useDatesContext();
  return (0, import_jsx_runtime20.jsx)(
    Calendar,
    {
      ref,
      minLevel: "decade",
      __updateDateOnYearSelect: __updateDateOnYearSelect ?? false,
      __staticSelector: __staticSelector || "YearPicker",
      onMouseLeave: onRootMouseLeave,
      onYearMouseEnter: (_event, date) => onHoveredDateChange(date),
      onYearSelect: (date) => {
        onDateChange(date);
        onYearSelect == null ? void 0 : onYearSelect(date);
      },
      getYearControlProps: (date) => ({
        ...getControlProps(date),
        ...getYearControlProps == null ? void 0 : getYearControlProps(date)
      }),
      classNames: resolvedClassNames,
      styles: resolvedStyles,
      ...others,
      date: shiftTimezone("add", others.date, ctx.getTimezone(), __timezoneApplied),
      __timezoneApplied: true
    }
  );
});
YearPicker.classes = Calendar.classes;
YearPicker.displayName = "@mantine/dates/YearPicker";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthPicker/MonthPicker.mjs
var import_jsx_runtime21 = __toESM(require_jsx_runtime(), 1);
var import_dayjs35 = __toESM(require_dayjs_min(), 1);
var import_react10 = __toESM(require_react(), 1);
var defaultProps19 = {
  type: "default"
};
var MonthPicker = factory((_props, ref) => {
  const props = useProps("MonthPicker", defaultProps19, _props);
  const {
    classNames,
    styles,
    vars,
    type,
    defaultValue,
    value,
    onChange,
    __staticSelector,
    getMonthControlProps,
    allowSingleDateInRange,
    allowDeselect,
    onMouseLeave,
    onMonthSelect,
    __updateDateOnMonthSelect,
    __timezoneApplied,
    onLevelChange,
    ...others
  } = props;
  const { onDateChange, onRootMouseLeave, onHoveredDateChange, getControlProps } = useDatesState({
    type,
    level: "month",
    allowDeselect,
    allowSingleDateInRange,
    value,
    defaultValue,
    onChange,
    onMouseLeave,
    applyTimezone: !__timezoneApplied
  });
  const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
    classNames,
    styles,
    props
  });
  const ctx = useDatesContext();
  return (0, import_jsx_runtime21.jsx)(
    Calendar,
    {
      ref,
      minLevel: "year",
      __updateDateOnMonthSelect: __updateDateOnMonthSelect ?? false,
      __staticSelector: __staticSelector || "MonthPicker",
      onMouseLeave: onRootMouseLeave,
      onMonthMouseEnter: (_event, date) => onHoveredDateChange(date),
      onMonthSelect: (date) => {
        onDateChange(date);
        onMonthSelect == null ? void 0 : onMonthSelect(date);
      },
      getMonthControlProps: (date) => ({
        ...getControlProps(date),
        ...getMonthControlProps == null ? void 0 : getMonthControlProps(date)
      }),
      classNames: resolvedClassNames,
      styles: resolvedStyles,
      onLevelChange,
      ...others,
      date: shiftTimezone("add", others.date, ctx.getTimezone(), __timezoneApplied),
      __timezoneApplied: true
    }
  );
});
MonthPicker.classes = Calendar.classes;
MonthPicker.displayName = "@mantine/dates/MonthPicker";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DatePicker/DatePicker.mjs
var import_jsx_runtime22 = __toESM(require_jsx_runtime(), 1);
var import_dayjs36 = __toESM(require_dayjs_min(), 1);
var import_react11 = __toESM(require_react(), 1);
var defaultProps20 = {
  type: "default",
  defaultLevel: "month",
  numberOfColumns: 1
};
var DatePicker = factory((_props, ref) => {
  const props = useProps("DatePicker", defaultProps20, _props);
  const {
    classNames,
    styles,
    vars,
    type,
    defaultValue,
    value,
    onChange,
    __staticSelector,
    getDayProps,
    allowSingleDateInRange,
    allowDeselect,
    onMouseLeave,
    numberOfColumns,
    hideOutsideDates,
    __onDayMouseEnter,
    __onDayClick,
    __timezoneApplied,
    ...others
  } = props;
  const { onDateChange, onRootMouseLeave, onHoveredDateChange, getControlProps } = useDatesState({
    type,
    level: "day",
    allowDeselect,
    allowSingleDateInRange,
    value,
    defaultValue,
    onChange,
    onMouseLeave,
    applyTimezone: !__timezoneApplied
  });
  const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
    classNames,
    styles,
    props
  });
  const ctx = useDatesContext();
  return (0, import_jsx_runtime22.jsx)(
    Calendar,
    {
      ref,
      minLevel: "month",
      classNames: resolvedClassNames,
      styles: resolvedStyles,
      __staticSelector: __staticSelector || "DatePicker",
      onMouseLeave: onRootMouseLeave,
      numberOfColumns,
      hideOutsideDates: hideOutsideDates ?? numberOfColumns !== 1,
      __onDayMouseEnter: (_event, date) => {
        onHoveredDateChange(date);
        __onDayMouseEnter == null ? void 0 : __onDayMouseEnter(_event, date);
      },
      __onDayClick: (_event, date) => {
        onDateChange(date);
        __onDayClick == null ? void 0 : __onDayClick(_event, date);
      },
      getDayProps: (date) => ({
        ...getControlProps(date),
        ...getDayProps == null ? void 0 : getDayProps(date)
      }),
      ...others,
      date: shiftTimezone("add", others.date, ctx.getTimezone(), __timezoneApplied),
      __timezoneApplied: true
    }
  );
});
DatePicker.classes = Calendar.classes;
DatePicker.displayName = "@mantine/dates/DatePicker";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DateInput/DateInput.mjs
var import_jsx_runtime23 = __toESM(require_jsx_runtime(), 1);
var import_dayjs39 = __toESM(require_dayjs_min(), 1);
var import_react12 = __toESM(require_react(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DateInput/date-string-parser/date-string-parser.mjs
var import_dayjs37 = __toESM(require_dayjs_min(), 1);
function dateStringParser(dateString, timezone) {
  if (dateString === null) {
    return null;
  }
  const date = shiftTimezone("add", new Date(dateString), timezone);
  if (Number.isNaN(date.getTime()) || !dateString) {
    return null;
  }
  return date;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DateInput/is-date-valid/is-date-valid.mjs
var import_dayjs38 = __toESM(require_dayjs_min(), 1);
function isDateValid({ date, maxDate, minDate }) {
  if (date == null) {
    return false;
  }
  if (Number.isNaN(date.getTime())) {
    return false;
  }
  if (maxDate && (0, import_dayjs38.default)(date).isAfter(maxDate, "date")) {
    return false;
  }
  if (minDate && (0, import_dayjs38.default)(date).isBefore(minDate, "date")) {
    return false;
  }
  return true;
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DateInput/DateInput.mjs
var defaultProps21 = {
  valueFormat: "MMMM D, YYYY",
  fixOnBlur: true,
  preserveTime: true
};
var DateInput = factory((_props, ref) => {
  const props = useInputProps("DateInput", defaultProps21, _props);
  const {
    inputProps,
    wrapperProps,
    value,
    defaultValue,
    onChange,
    clearable,
    clearButtonProps,
    popoverProps,
    getDayProps,
    locale,
    valueFormat,
    dateParser,
    minDate,
    maxDate,
    fixOnBlur,
    onFocus,
    onBlur,
    onClick,
    onKeyDown,
    readOnly,
    name,
    form,
    rightSection,
    unstyled,
    classNames,
    styles,
    allowDeselect,
    preserveTime,
    date,
    defaultDate,
    onDateChange,
    ...rest
  } = props;
  const _wrapperRef = (0, import_react12.useRef)(null);
  const _dropdownRef = (0, import_react12.useRef)(null);
  const [dropdownOpened, setDropdownOpened] = (0, import_react12.useState)(false);
  const { calendarProps, others } = pickCalendarProps(rest);
  const ctx = useDatesContext();
  const defaultDateParser = (val) => {
    const parsedDate = (0, import_dayjs39.default)(val, valueFormat, ctx.getLocale(locale)).toDate();
    return Number.isNaN(parsedDate.getTime()) ? dateStringParser(val, ctx.getTimezone()) : parsedDate;
  };
  const _dateParser = dateParser || defaultDateParser;
  const _allowDeselect = allowDeselect !== void 0 ? allowDeselect : clearable;
  const formatValue2 = (val) => val ? (0, import_dayjs39.default)(val).locale(ctx.getLocale(locale)).format(valueFormat) : "";
  const [_value, setValue, controlled] = useUncontrolledDates({
    type: "default",
    value,
    defaultValue,
    onChange
  });
  const [_date, setDate] = useUncontrolledDates({
    type: "default",
    value: date,
    defaultValue: defaultValue || defaultDate,
    onChange: onDateChange
  });
  (0, import_react12.useEffect)(() => {
    if (controlled && value !== null) {
      setDate(value);
    }
  }, [controlled, value]);
  const [inputValue, setInputValue] = (0, import_react12.useState)(formatValue2(_value));
  (0, import_react12.useEffect)(() => {
    setInputValue(formatValue2(_value));
  }, [ctx.getLocale(locale)]);
  const handleInputChange = (event) => {
    const val = event.currentTarget.value;
    setInputValue(val);
    setDropdownOpened(true);
    if (val.trim() === "" && clearable) {
      setValue(null);
    } else {
      const dateValue = _dateParser(val);
      if (isDateValid({ date: dateValue, minDate, maxDate })) {
        setValue(dateValue);
        setDate(dateValue);
      }
    }
  };
  const handleInputBlur = (event) => {
    onBlur == null ? void 0 : onBlur(event);
    setDropdownOpened(false);
    fixOnBlur && setInputValue(formatValue2(_value));
  };
  const handleInputFocus = (event) => {
    onFocus == null ? void 0 : onFocus(event);
    setDropdownOpened(true);
  };
  const handleInputClick = (event) => {
    onClick == null ? void 0 : onClick(event);
    setDropdownOpened(true);
  };
  const handleInputKeyDown = (event) => {
    if (event.key === "Escape") {
      setDropdownOpened(false);
    }
    onKeyDown == null ? void 0 : onKeyDown(event);
  };
  const _getDayProps = (day) => ({
    ...getDayProps == null ? void 0 : getDayProps(day),
    selected: (0, import_dayjs39.default)(_value).isSame(day, "day"),
    onClick: (event) => {
      var _a, _b;
      (_b = getDayProps == null ? void 0 : (_a = getDayProps(day)).onClick) == null ? void 0 : _b.call(_a, event);
      const valueWithTime = preserveTime ? assignTime(_value, day) : day;
      const val = clearable && _allowDeselect ? (0, import_dayjs39.default)(_value).isSame(day, "day") ? null : valueWithTime : valueWithTime;
      setValue(val);
      !controlled && setInputValue(formatValue2(val));
      setDropdownOpened(false);
    }
  });
  const _rightSection = rightSection || (clearable && _value && !readOnly ? (0, import_jsx_runtime23.jsx)(
    CloseButton,
    {
      variant: "transparent",
      onMouseDown: (event) => event.preventDefault(),
      tabIndex: -1,
      onClick: () => {
        setValue(null);
        !controlled && setInputValue("");
        setDropdownOpened(false);
      },
      unstyled,
      size: inputProps.size || "sm",
      ...clearButtonProps
    }
  ) : null);
  useDidUpdate(() => {
    _value !== void 0 && !dropdownOpened && setInputValue(formatValue2(_value));
  }, [_value]);
  useClickOutside(() => setDropdownOpened(false), void 0, [
    _wrapperRef.current,
    _dropdownRef.current
  ]);
  return (0, import_jsx_runtime23.jsxs)(import_jsx_runtime23.Fragment, { children: [
    (0, import_jsx_runtime23.jsx)(Input.Wrapper, { ...wrapperProps, __staticSelector: "DateInput", ref: _wrapperRef, children: (0, import_jsx_runtime23.jsxs)(
      Popover,
      {
        opened: dropdownOpened,
        trapFocus: false,
        position: "bottom-start",
        disabled: readOnly,
        withRoles: false,
        unstyled,
        ...popoverProps,
        children: [
          (0, import_jsx_runtime23.jsx)(Popover.Target, { children: (0, import_jsx_runtime23.jsx)(
            Input,
            {
              "data-dates-input": true,
              "data-read-only": readOnly || void 0,
              autoComplete: "off",
              ref,
              value: inputValue,
              onChange: handleInputChange,
              onBlur: handleInputBlur,
              onFocus: handleInputFocus,
              onClick: handleInputClick,
              onKeyDown: handleInputKeyDown,
              readOnly,
              rightSection: _rightSection,
              ...inputProps,
              ...others,
              __staticSelector: "DateInput"
            }
          ) }),
          (0, import_jsx_runtime23.jsx)(
            Popover.Dropdown,
            {
              onMouseDown: (event) => event.preventDefault(),
              "data-dates-dropdown": true,
              ref: _dropdownRef,
              children: (0, import_jsx_runtime23.jsx)(
                Calendar,
                {
                  __staticSelector: "DateInput",
                  __timezoneApplied: true,
                  ...calendarProps,
                  classNames,
                  styles,
                  unstyled,
                  __preventFocus: true,
                  minDate,
                  maxDate,
                  locale,
                  getDayProps: _getDayProps,
                  size: inputProps.size,
                  date: _date,
                  onDateChange: setDate
                }
              )
            }
          )
        ]
      }
    ) }),
    (0, import_jsx_runtime23.jsx)(HiddenDatesInput, { name, form, value: _value, type: "default" })
  ] });
});
DateInput.classes = { ...Input.classes, ...Calendar.classes };
DateInput.displayName = "@mantine/dates/DateInput";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DateTimePicker/DateTimePicker.mjs
var import_jsx_runtime24 = __toESM(require_jsx_runtime(), 1);
var import_dayjs40 = __toESM(require_dayjs_min(), 1);
var import_react13 = __toESM(require_react(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DateTimePicker/DateTimePicker.module.css.mjs
var classes11 = { "timeWrapper": "m_208d2562", "timeInput": "m_62ee059" };

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DateTimePicker/DateTimePicker.mjs
var defaultProps22 = {
  dropdownType: "popover"
};
var DateTimePicker = factory((_props, ref) => {
  const props = useProps("DateTimePicker", defaultProps22, _props);
  const {
    value,
    defaultValue,
    onChange,
    valueFormat,
    locale,
    classNames,
    styles,
    unstyled,
    timeInputProps,
    submitButtonProps,
    withSeconds,
    level,
    defaultLevel,
    size,
    variant,
    dropdownType,
    vars,
    minDate,
    maxDate,
    ...rest
  } = props;
  const getStyles = useStyles({
    name: "DateTimePicker",
    classes: classes11,
    props,
    classNames,
    styles,
    unstyled,
    vars
  });
  const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
    classNames,
    styles,
    props
  });
  const _valueFormat = valueFormat || (withSeconds ? "DD/MM/YYYY HH:mm:ss" : "DD/MM/YYYY HH:mm");
  const timeInputRef = (0, import_react13.useRef)(null);
  const timeInputRefMerged = useMergedRef(timeInputRef, timeInputProps == null ? void 0 : timeInputProps.ref);
  const {
    calendarProps: { allowSingleDateInRange, ...calendarProps },
    others
  } = pickCalendarProps(rest);
  const ctx = useDatesContext();
  const [_value, setValue] = useUncontrolledDates({
    type: "default",
    value,
    defaultValue,
    onChange
  });
  const formatTime = (dateValue) => dateValue ? (0, import_dayjs40.default)(dateValue).format(withSeconds ? "HH:mm:ss" : "HH:mm") : "";
  const [timeValue, setTimeValue] = (0, import_react13.useState)(formatTime(_value));
  const [currentLevel, setCurrentLevel] = (0, import_react13.useState)(level || defaultLevel || "month");
  const [dropdownOpened, dropdownHandlers] = useDisclosure(false);
  const formattedValue = _value ? (0, import_dayjs40.default)(_value).locale(ctx.getLocale(locale)).tz(ctx.getTimezone(), true).format(_valueFormat) : "";
  const handleTimeChange = (event) => {
    var _a;
    (_a = timeInputProps == null ? void 0 : timeInputProps.onChange) == null ? void 0 : _a.call(timeInputProps, event);
    const val = event.currentTarget.value;
    setTimeValue(val);
    if (val) {
      const [hours, minutes, seconds] = val.split(":").map(Number);
      const timeDate = shiftTimezone("add", /* @__PURE__ */ new Date(), ctx.getTimezone());
      timeDate.setHours(hours);
      timeDate.setMinutes(minutes);
      timeDate.setSeconds(seconds || 0);
      timeDate.setMilliseconds(0);
      setValue(assignTime(timeDate, _value || shiftTimezone("add", /* @__PURE__ */ new Date(), ctx.getTimezone())));
    }
  };
  const handleDateChange = (date) => {
    var _a;
    if (date) {
      setValue(assignTime(_value, date));
    }
    (_a = timeInputRef.current) == null ? void 0 : _a.focus();
  };
  const handleTimeInputKeyDown = (event) => {
    var _a;
    (_a = timeInputProps == null ? void 0 : timeInputProps.onKeyDown) == null ? void 0 : _a.call(timeInputProps, event);
    if (event.key === "Enter") {
      event.preventDefault();
      dropdownHandlers.close();
    }
  };
  useDidUpdate(() => {
    if (!dropdownOpened) {
      setTimeValue(formatTime(_value));
    }
  }, [_value, dropdownOpened]);
  useDidUpdate(() => {
    if (dropdownOpened) {
      setCurrentLevel("month");
    }
  }, [dropdownOpened]);
  const minTime = minDate ? (0, import_dayjs40.default)(minDate).format("HH:mm:ss") : null;
  const maxTime = maxDate ? (0, import_dayjs40.default)(maxDate).format("HH:mm:ss") : null;
  const __stopPropagation = dropdownType === "popover";
  return (0, import_jsx_runtime24.jsxs)(
    PickerInputBase,
    {
      formattedValue,
      dropdownOpened: !rest.disabled ? dropdownOpened : false,
      dropdownHandlers,
      classNames: resolvedClassNames,
      styles: resolvedStyles,
      unstyled,
      ref,
      onClear: () => setValue(null),
      shouldClear: !!_value,
      value: _value,
      size,
      variant,
      dropdownType,
      ...others,
      type: "default",
      __staticSelector: "DateTimePicker",
      children: [
        (0, import_jsx_runtime24.jsx)(
          DatePicker,
          {
            ...calendarProps,
            maxDate,
            minDate,
            size,
            variant,
            type: "default",
            value: _value,
            defaultDate: _value,
            onChange: handleDateChange,
            locale,
            classNames: resolvedClassNames,
            styles: resolvedStyles,
            unstyled,
            __staticSelector: "DateTimePicker",
            __stopPropagation,
            level,
            defaultLevel,
            onLevelChange: (_level) => {
              var _a;
              setCurrentLevel(_level);
              (_a = calendarProps.onLevelChange) == null ? void 0 : _a.call(calendarProps, _level);
            },
            __timezoneApplied: true
          }
        ),
        currentLevel === "month" && (0, import_jsx_runtime24.jsxs)("div", { ...getStyles("timeWrapper"), children: [
          (0, import_jsx_runtime24.jsx)(
            TimeInput,
            {
              value: timeValue,
              withSeconds,
              ref: timeInputRefMerged,
              unstyled,
              minTime: _value && minDate && _value.toDateString() === minDate.toDateString() ? minTime != null ? minTime : void 0 : void 0,
              maxTime: _value && maxDate && _value.toDateString() === maxDate.toDateString() ? maxTime != null ? maxTime : void 0 : void 0,
              ...timeInputProps,
              ...getStyles("timeInput", {
                className: timeInputProps == null ? void 0 : timeInputProps.className,
                style: timeInputProps == null ? void 0 : timeInputProps.style
              }),
              onChange: handleTimeChange,
              onKeyDown: handleTimeInputKeyDown,
              size,
              "data-mantine-stop-propagation": __stopPropagation || void 0
            }
          ),
          (0, import_jsx_runtime24.jsx)(
            ActionIcon,
            {
              variant: "default",
              size: `input-${size || "sm"}`,
              ...getStyles("submitButton", {
                className: submitButtonProps == null ? void 0 : submitButtonProps.className,
                style: submitButtonProps == null ? void 0 : submitButtonProps.style
              }),
              unstyled,
              "data-mantine-stop-propagation": __stopPropagation || void 0,
              children: (0, import_jsx_runtime24.jsx)(CheckIcon, { size: "30%" }),
              ...submitButtonProps,
              onClick: (event) => {
                var _a;
                (_a = submitButtonProps == null ? void 0 : submitButtonProps.onClick) == null ? void 0 : _a.call(submitButtonProps, event);
                dropdownHandlers.close();
              }
            }
          )
        ] })
      ]
    }
  );
});
DateTimePicker.classes = { ...classes11, ...PickerInputBase.classes, ...DatePicker.classes };
DateTimePicker.displayName = "@mantine/dates/DateTimePicker";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearPickerInput/YearPickerInput.mjs
var import_jsx_runtime25 = __toESM(require_jsx_runtime(), 1);
var import_dayjs42 = __toESM(require_dayjs_min(), 1);
var import_react14 = __toESM(require_react(), 1);

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/hooks/use-dates-input/use-dates-input.mjs
var import_dayjs41 = __toESM(require_dayjs_min(), 1);
function useDatesInput({
  type,
  value,
  defaultValue,
  onChange,
  locale,
  format,
  closeOnChange,
  sortDates,
  labelSeparator,
  valueFormatter
}) {
  const ctx = useDatesContext();
  const [dropdownOpened, dropdownHandlers] = useDisclosure(false);
  const [_value, _setValue] = useUncontrolledDates({
    type,
    value,
    defaultValue,
    onChange
  });
  const formattedValue = getFormattedDate({
    type,
    date: _value,
    locale: ctx.getLocale(locale),
    format,
    labelSeparator: ctx.getLabelSeparator(labelSeparator),
    formatter: valueFormatter
  });
  const setValue = (val) => {
    if (closeOnChange) {
      if (type === "default") {
        dropdownHandlers.close();
      }
      if (type === "range" && val[0] && val[1]) {
        dropdownHandlers.close();
      }
    }
    if (sortDates && type === "multiple") {
      _setValue([...val].sort((a, b) => a.getTime() - b.getTime()));
    } else {
      _setValue(val);
    }
  };
  const onClear = () => setValue(type === "range" ? [null, null] : type === "multiple" ? [] : null);
  const shouldClear = type === "range" ? !!_value[0] : type === "multiple" ? _value.length > 0 : _value !== null;
  return {
    _value,
    setValue,
    onClear,
    shouldClear,
    formattedValue,
    dropdownOpened,
    dropdownHandlers
  };
}

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/YearPickerInput/YearPickerInput.mjs
var defaultProps23 = {
  type: "default",
  valueFormat: "YYYY",
  closeOnChange: true,
  sortDates: true,
  dropdownType: "popover"
};
var YearPickerInput = factory(
  (_props, ref) => {
    const props = useProps("YearPickerInput", defaultProps23, _props);
    const {
      type,
      value,
      defaultValue,
      onChange,
      valueFormat,
      labelSeparator,
      locale,
      classNames,
      styles,
      unstyled,
      closeOnChange,
      size,
      variant,
      dropdownType,
      sortDates,
      minDate,
      maxDate,
      vars,
      valueFormatter,
      ...rest
    } = props;
    const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
      classNames,
      styles,
      props
    });
    const { calendarProps, others } = pickCalendarProps(rest);
    const ctx = useDatesContext();
    const {
      _value,
      setValue,
      formattedValue,
      dropdownHandlers,
      dropdownOpened,
      onClear,
      shouldClear
    } = useDatesInput({
      type,
      value,
      defaultValue,
      onChange,
      locale,
      format: valueFormat,
      labelSeparator,
      closeOnChange,
      sortDates,
      valueFormatter
    });
    return (0, import_jsx_runtime25.jsx)(
      PickerInputBase,
      {
        formattedValue,
        dropdownOpened,
        dropdownHandlers,
        classNames: resolvedClassNames,
        styles: resolvedStyles,
        unstyled,
        ref,
        onClear,
        shouldClear,
        value: _value,
        size,
        variant,
        dropdownType,
        ...others,
        type,
        __staticSelector: "YearPickerInput",
        children: (0, import_jsx_runtime25.jsx)(
          YearPicker,
          {
            ...calendarProps,
            size,
            variant,
            type,
            value: _value,
            defaultDate: calendarProps.defaultDate || (Array.isArray(_value) ? _value[0] || getDefaultClampedDate({ maxDate, minDate, timezone: ctx.getTimezone() }) : _value || getDefaultClampedDate({ maxDate, minDate, timezone: ctx.getTimezone() })),
            onChange: setValue,
            locale,
            classNames: resolvedClassNames,
            styles: resolvedStyles,
            unstyled,
            __staticSelector: "YearPickerInput",
            __stopPropagation: dropdownType === "popover",
            minDate,
            maxDate,
            date: shiftTimezone("add", calendarProps.date, ctx.getTimezone()),
            __timezoneApplied: true
          }
        )
      }
    );
  }
);
YearPickerInput.classes = { ...PickerInputBase.classes, ...YearPicker.classes };
YearPickerInput.displayName = "@mantine/dates/YearPickerInput";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/MonthPickerInput/MonthPickerInput.mjs
var import_jsx_runtime26 = __toESM(require_jsx_runtime(), 1);
var import_dayjs43 = __toESM(require_dayjs_min(), 1);
var import_react15 = __toESM(require_react(), 1);
var defaultProps24 = {
  type: "default",
  valueFormat: "MMMM YYYY",
  closeOnChange: true,
  sortDates: true,
  dropdownType: "popover"
};
var MonthPickerInput = factory(
  (_props, ref) => {
    const props = useProps("MonthPickerInput", defaultProps24, _props);
    const {
      type,
      value,
      defaultValue,
      onChange,
      valueFormat,
      labelSeparator,
      locale,
      classNames,
      styles,
      unstyled,
      closeOnChange,
      size,
      variant,
      dropdownType,
      sortDates,
      minDate,
      maxDate,
      vars,
      valueFormatter,
      ...rest
    } = props;
    const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
      classNames,
      styles,
      props
    });
    const { calendarProps, others } = pickCalendarProps(rest);
    const {
      _value,
      setValue,
      formattedValue,
      dropdownHandlers,
      dropdownOpened,
      onClear,
      shouldClear
    } = useDatesInput({
      type,
      value,
      defaultValue,
      onChange,
      locale,
      format: valueFormat,
      labelSeparator,
      closeOnChange,
      sortDates,
      valueFormatter
    });
    const ctx = useDatesContext();
    return (0, import_jsx_runtime26.jsx)(
      PickerInputBase,
      {
        formattedValue,
        dropdownOpened,
        dropdownHandlers,
        classNames: resolvedClassNames,
        styles: resolvedStyles,
        unstyled,
        ref,
        onClear,
        shouldClear,
        value: _value,
        size,
        variant,
        dropdownType,
        ...others,
        type,
        __staticSelector: "MonthPickerInput",
        children: (0, import_jsx_runtime26.jsx)(
          MonthPicker,
          {
            ...calendarProps,
            date: shiftTimezone("add", calendarProps.date, ctx.getTimezone()),
            size,
            variant,
            type,
            value: _value,
            defaultDate: calendarProps.defaultDate || (Array.isArray(_value) ? _value[0] || getDefaultClampedDate({ maxDate, minDate }) : _value || getDefaultClampedDate({ maxDate, minDate })),
            onChange: setValue,
            locale,
            classNames: resolvedClassNames,
            styles: resolvedStyles,
            unstyled,
            __staticSelector: "MonthPickerInput",
            __stopPropagation: dropdownType === "popover",
            minDate,
            maxDate,
            __timezoneApplied: true
          }
        )
      }
    );
  }
);
MonthPickerInput.classes = { ...PickerInputBase.classes, ...MonthPicker.classes };
MonthPickerInput.displayName = "@mantine/dates/MonthPickerInput";

// node_modules/.pnpm/@mantine+dates@7.17.8_@mantine+core@7.17.8_@mantine+hooks@7.17.8_react@18.3.1__@types+r_002b83e2d53b34ce986dd896d52c5e01/node_modules/@mantine/dates/esm/components/DatePickerInput/DatePickerInput.mjs
var import_jsx_runtime27 = __toESM(require_jsx_runtime(), 1);
var import_dayjs44 = __toESM(require_dayjs_min(), 1);
var import_react16 = __toESM(require_react(), 1);
var defaultProps25 = {
  type: "default",
  valueFormat: "MMMM D, YYYY",
  closeOnChange: true,
  sortDates: true,
  dropdownType: "popover"
};
var DatePickerInput = factory(
  (_props, ref) => {
    const props = useProps("DatePickerInput", defaultProps25, _props);
    const {
      type,
      value,
      defaultValue,
      onChange,
      valueFormat,
      labelSeparator,
      locale,
      classNames,
      styles,
      unstyled,
      closeOnChange,
      size,
      variant,
      dropdownType,
      sortDates,
      minDate,
      maxDate,
      vars,
      defaultDate,
      valueFormatter,
      ...rest
    } = props;
    const { resolvedClassNames, resolvedStyles } = useResolvedStylesApi({
      classNames,
      styles,
      props
    });
    const { calendarProps, others } = pickCalendarProps(rest);
    const {
      _value,
      setValue,
      formattedValue,
      dropdownHandlers,
      dropdownOpened,
      onClear,
      shouldClear
    } = useDatesInput({
      type,
      value,
      defaultValue,
      onChange,
      locale,
      format: valueFormat,
      labelSeparator,
      closeOnChange,
      sortDates,
      valueFormatter
    });
    const _defaultDate = Array.isArray(_value) ? _value[0] || defaultDate : _value || defaultDate;
    const ctx = useDatesContext();
    return (0, import_jsx_runtime27.jsx)(
      PickerInputBase,
      {
        formattedValue,
        dropdownOpened,
        dropdownHandlers,
        classNames: resolvedClassNames,
        styles: resolvedStyles,
        unstyled,
        ref,
        onClear,
        shouldClear,
        value: _value,
        size,
        variant,
        dropdownType,
        ...others,
        type,
        __staticSelector: "DatePickerInput",
        children: (0, import_jsx_runtime27.jsx)(
          DatePicker,
          {
            ...calendarProps,
            size,
            variant,
            type,
            value: _value,
            defaultDate: _defaultDate || getDefaultClampedDate({ maxDate, minDate, timezone: ctx.getTimezone() }),
            onChange: setValue,
            locale,
            classNames: resolvedClassNames,
            styles: resolvedStyles,
            unstyled,
            __staticSelector: "DatePickerInput",
            __stopPropagation: dropdownType === "popover",
            minDate,
            maxDate,
            date: shiftTimezone("add", calendarProps.date, ctx.getTimezone()),
            __timezoneApplied: true
          }
        )
      }
    );
  }
);
DatePickerInput.classes = { ...PickerInputBase.classes, ...DatePicker.classes };
DatePickerInput.displayName = "@mantine/dates/DatePickerInput";

export {
  getFormattedDate,
  handleControlKeyDown,
  assignTime,
  shiftTimezone,
  getDefaultClampedDate,
  DATES_PROVIDER_DEFAULT_SETTINGS,
  DatesProvider,
  useDatesContext,
  HiddenDatesInput,
  TimeInput,
  Day,
  WeekdaysRow,
  getEndOfWeek,
  getStartOfWeek,
  getMonthDays,
  isSameMonth,
  Month,
  PickerControl,
  YearsList,
  MonthsList,
  CalendarHeader,
  DecadeLevel,
  YearLevel,
  MonthLevel,
  LevelsGroup,
  DecadeLevelGroup,
  YearLevelGroup,
  MonthLevelGroup,
  PickerInputBase,
  Calendar,
  pickCalendarProps,
  YearPicker,
  MonthPicker,
  DatePicker,
  DateInput,
  DateTimePicker,
  YearPickerInput,
  MonthPickerInput,
  DatePickerInput
};
//# sourceMappingURL=chunk-5CZMG6BE.js.map
