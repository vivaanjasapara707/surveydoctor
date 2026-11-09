import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'
import { describe, expect, it } from 'vitest'
import { COLORS } from './tokens'

// Tests run from the frontend folder.
const css = readFileSync(resolve(process.cwd(), 'src/styles/global.css'), 'utf8')

describe('chart colours', () => {
  it.each(Object.entries(COLORS))('%s matches the token in global.css', (name, hex) => {
    const match = new RegExp(`--color-${name}:\\s*(#[0-9a-fA-F]{6});`).exec(css)
    expect(match?.[1].toLowerCase()).toBe(hex)
  })
})
