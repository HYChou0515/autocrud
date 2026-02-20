.PHONY: install dev build preview test clean style

install:
	pnpm install

dev:
	pnpm dev

build:
	pnpm build

preview:
	pnpm preview

test:
	pnpm exec vitest run

test-watch:
	pnpm exec vitest

coverage:
	pnpm exec vitest run --coverage

style:
	pnpm exec prettier --write "src/**/*.{ts,tsx}"
	pnpm exec eslint --fix src/

clean:
	rm -rf dist node_modules
