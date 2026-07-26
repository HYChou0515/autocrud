import { describe, it, expect } from 'vitest';
import {
  DEFAULT_APP_TITLE,
  DEFAULT_APP_LOGO,
  resolveBranding,
  renderBrandingModule,
  patchIndexHtml,
} from './branding.js';

describe('branding', () => {
  // ---------------------------------------------------------------------------
  // resolveBranding — precedence: .specstarrc.json > OpenAPI info.title > default
  // ---------------------------------------------------------------------------

  describe('resolveBranding', () => {
    it('falls back to the SpecStar defaults when nothing is configured', () => {
      expect(resolveBranding({})).toEqual({
        title: DEFAULT_APP_TITLE,
        logo: DEFAULT_APP_LOGO,
      });
    });

    it("uses the OpenAPI info.title when the project hasn't overridden it", () => {
      expect(resolveBranding({ specTitle: 'RPG Game API' }).title).toBe('RPG Game API');
    });

    it('lets .specstarrc.json win over the OpenAPI info.title', () => {
      expect(resolveBranding({ rc: { title: 'My Console' }, specTitle: 'RPG Game API' }).title).toBe('My Console');
    });

    it('lets .specstarrc.json override the logo', () => {
      expect(resolveBranding({ rc: { logo: '/brand/acme.svg' } }).logo).toBe('/brand/acme.svg');
    });

    it('keeps the default logo when only the title is overridden', () => {
      expect(resolveBranding({ rc: { title: 'My Console' } }).logo).toBe(DEFAULT_APP_LOGO);
    });

    it('trims surrounding whitespace', () => {
      expect(resolveBranding({ specTitle: '  Spaced API  ' }).title).toBe('Spaced API');
    });

    // A blank string is a *present but meaningless* value — treating it as an
    // override would leave the browser tab with an empty name.
    it('ignores a blank rc title and falls through to the spec title', () => {
      expect(resolveBranding({ rc: { title: '   ' }, specTitle: 'RPG Game API' }).title).toBe('RPG Game API');
    });

    it('ignores a blank spec title and falls through to the default', () => {
      expect(resolveBranding({ specTitle: '' }).title).toBe(DEFAULT_APP_TITLE);
    });

    it('ignores a blank rc logo and falls through to the default', () => {
      expect(resolveBranding({ rc: { logo: '  ' } }).logo).toBe(DEFAULT_APP_LOGO);
    });

    // FastAPI stamps this on every app that never set a title; it carries no
    // information, so it must not beat the SpecStar default.
    it('ignores the stock FastAPI placeholder title', () => {
      expect(resolveBranding({ specTitle: 'FastAPI' }).title).toBe(DEFAULT_APP_TITLE);
    });
  });

  // ---------------------------------------------------------------------------
  // renderBrandingModule
  // ---------------------------------------------------------------------------

  describe('renderBrandingModule', () => {
    it('exports the resolved title and logo', () => {
      const out = renderBrandingModule({ title: 'RPG Game API', logo: '/specstar-mark.svg' });
      expect(out).toContain("export const APP_TITLE = 'RPG Game API';");
      expect(out).toContain("export const APP_LOGO = '/specstar-mark.svg';");
    });

    it('escapes quotes so an apostrophe in the title cannot break the module', () => {
      const out = renderBrandingModule({ title: "Ann's API", logo: '/l.svg' });
      expect(out).toContain("export const APP_TITLE = 'Ann\\'s API';");
    });
  });

  // ---------------------------------------------------------------------------
  // patchIndexHtml
  // ---------------------------------------------------------------------------

  describe('patchIndexHtml', () => {
    const html = [
      '<!DOCTYPE html>',
      '<html lang="en">',
      '  <head>',
      '    <meta charset="UTF-8" />',
      '    <link rel="icon" type="image/svg+xml" href="/vite.svg" />',
      '    <title>SpecStar Admin</title>',
      '  </head>',
      '</html>',
    ].join('\n');

    it('rewrites the document title', () => {
      expect(patchIndexHtml(html, { title: 'RPG Game API', logo: '/specstar-mark.svg' })).toContain(
        '<title>RPG Game API</title>',
      );
    });

    it('rewrites the favicon href', () => {
      const out = patchIndexHtml(html, { title: 'X', logo: '/specstar-mark.svg' });
      expect(out).toContain('href="/specstar-mark.svg"');
      expect(out).not.toContain('/vite.svg');
    });

    it('escapes HTML-special characters in the title', () => {
      const out = patchIndexHtml(html, { title: 'A & B <Ops>', logo: '/l.svg' });
      expect(out).toContain('<title>A &amp; B &lt;Ops&gt;</title>');
    });

    // Leaving type="image/svg+xml" on a .png favicon makes browsers refuse it.
    it('retypes the favicon link to match the overridden logo extension', () => {
      const out = patchIndexHtml(html, { title: 'X', logo: '/brand/acme.png' });
      expect(out).toContain('type="image/png"');
      expect(out).not.toContain('image/svg+xml');
    });

    it('drops the type attribute when the logo extension is unknown', () => {
      const out = patchIndexHtml(html, { title: 'X', logo: '/brand/acme' });
      expect(out).not.toContain('type=');
      expect(out).toContain('href="/brand/acme"');
    });

    it('is idempotent — patching twice gives the same result', () => {
      const branding = { title: 'RPG Game API', logo: '/specstar-mark.svg' };
      const once = patchIndexHtml(html, branding);
      expect(patchIndexHtml(once, branding)).toBe(once);
    });

    it('leaves html without a title or icon link untouched', () => {
      const bare = '<html><head><meta charset="UTF-8" /></head></html>';
      expect(patchIndexHtml(bare, { title: 'X', logo: '/l.svg' })).toBe(bare);
    });
  });
});
