import { describe, expect, it } from 'vitest'
import { checkFile } from './upload'

function fileOfSize(size: number) {
  const file = new File(['a'], 'survey.csv', { type: 'text/csv' })
  Object.defineProperty(file, 'size', { value: size })
  return file
}

describe('checkFile', () => {
  it('accepts a file within the limit', () => {
    expect(checkFile(fileOfSize(10 * 1024 * 1024))).toBeNull()
  })

  it('refuses a file over 10 MB before sending it', () => {
    expect(checkFile(fileOfSize(12 * 1024 * 1024))).toMatch(
      /^The file is larger than 10 MB\..*\(This file is 12\.0 MB\.\)$/,
    )
  })

  it('refuses an empty file', () => {
    expect(checkFile(fileOfSize(0))).toBe(
      'The file is empty. Choose the CSV file with your responses.',
    )
  })
})
