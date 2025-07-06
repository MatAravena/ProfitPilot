/* eslint no-console: 0 */
import { en } from './en';
import { de } from './de';
import { es } from './es';

/** HELPER FUNCTIONS */
const allTranslationsPresent = () => {
  const languages: Record<string, Record<string, string>> = {
    en,
    de,
    es,
  };
  // get set of all possible keys
  const init: string[] = [];
  const keySet = new Set(
    Object.values(languages).reduce(
      (keys, l) => keys.concat(Object.keys(l)),
      init,
    ),
  );

  for (const lang in languages) {
    const notTranslated: string[] = [];
    keySet.forEach(key => {
      if (!(key in languages[lang])) notTranslated.push(key);
    });
    if (notTranslated.length) {
      console.error(
        'MISSING TRANSLATIONS in ' +
          lang +
          ':\n' +
          notTranslated.reduce((prev, curr) => (prev += curr + '\n'), ''),
      );
      return false;
    } else {
      return true;
    }
  }
  return true;
};

describe('Languages test', () => {
  test('has all strings translated', () => {
    expect(allTranslationsPresent()).toBe(true);
  });
});
