# SurveyDoctor website

The React + TypeScript front end of SurveyDoctor (BLUEPRINT §7.12). It computes no statistics: it sends the CSV to the API and shows what comes back. How to run it: see "Run the website locally" in the main `README.md`.

| Command           | What it does                                                          |
| ----------------- | --------------------------------------------------------------------- |
| `npm run dev`     | Development server at http://localhost:5173                           |
| `npm test`        | Component and unit tests (Vitest)                                     |
| `npm run lint`    | ESLint                                                                |
| `npm run format`  | Prettier                                                              |
| `npm run build`   | Type-check and build to `dist/`                                       |
| `npm run gen:api` | Regenerate `src/api/schema.ts` from the running API's `/openapi.json` |

- `src/api/schema.ts` is generated; never edit it by hand.
- Colours, fonts and type sizes are the tokens from `docs/design.md`, defined in `src/styles/global.css`. Tailwind's default palette is switched off, so only these tokens can be used.
- The IBM Plex fonts in `src/styles/fonts/` are the same files as the HTML report's (SIL Open Font Licence, see `LICENSE.txt` there).
