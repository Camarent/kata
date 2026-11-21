// Local stop patterns: a text matches when any pattern (a regular expression source) matches it.
// A pattern that is not a valid regular expression is skipped, never thrown.
export function matchesStop(text: string, patterns: string[]): boolean {
  for (const source of patterns) {
    let re: RegExp;
    try {
      re = new RegExp(source);
    } catch {
      continue;
    }
    if (re.test(text)) {
      return true;
    }
  }
  return false;
}
