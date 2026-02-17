import {
  $ZodError,
  parse
} from "./chunk-GJOL5HO3.js";
import "./chunk-G3PMV62Z.js";

// node_modules/.pnpm/mantine-form-zod-resolver@1.3.0_@mantine+form@7.17.8_react@18.3.1__zod@4.3.6/node_modules/mantine-form-zod-resolver/dist/esm/index.mjs
function zodResolver(schema, options) {
  return (values) => {
    const parsed = schema.safeParse(values);
    if (parsed.success) {
      return {};
    }
    const results = {};
    if ("error" in parsed) {
      if ((options == null ? void 0 : options.errorPriority) === "first") {
        parsed.error.errors.reverse();
      }
      parsed.error.errors.forEach((error) => {
        results[error.path.join(".")] = error.message;
      });
    }
    return results;
  };
}
function zod4Resolver(schema, options) {
  return (values) => {
    try {
      parse(schema, values);
      return {};
    } catch (error) {
      if (error instanceof $ZodError) {
        const results = {};
        if ((options == null ? void 0 : options.errorPriority) === "first") {
          error.issues.reverse();
        }
        error.issues.forEach((issue) => {
          results[issue.path.join(".")] = issue.message;
        });
        return results;
      }
      throw error;
    }
  };
}
export {
  zod4Resolver,
  zodResolver
};
//# sourceMappingURL=mantine-form-zod-resolver.js.map
