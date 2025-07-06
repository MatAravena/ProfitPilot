import languages, {
  getBrowserLanguage,
  getFallbackLanguage,
  isLanguage,
  KnownLanguages,
} from '@hooks/languages';


import React, { useCallback, useMemo } from 'react';
import { useSelector } from 'react-redux';
import { isDev, isKeyof, isLocalhost } from '../lib/utils';
import ReactDOMServer from 'react-dom/server';
import { userLanguageSelector, userLocaleSelector } from '../core/store/selectors/userSelectors';

export const getLanguage = (
  lang: string,
  deviations?: Record<string, any> | null,
): KnownLanguages => {
  const adjustedLang = `${lang}${deviations?.LANGUAGE_SUFFIX?.value || ''}`;

  if (isLanguage(adjustedLang)) {
    return adjustedLang;
  }

  if (isLanguage(lang)) {
    return lang;
  }

  const trimmedLang = lang.substring(0, 2);

  const adjustedTrimmedLang = `${trimmedLang}${
    deviations?.LANGUAGE_SUFFIX?.value || ''
  }`;

  if (isLanguage(adjustedTrimmedLang)) {
    return adjustedTrimmedLang;
  }

  if (isLanguage(trimmedLang)) {
    return trimmedLang;
  }

  return 'de';
};

export const useTranslation = () => {
  const userLanguage = useSelector(userLanguageSelector);
  const userLocale = useSelector(userLocaleSelector);

  const language = useMemo(() => {

    //userLanguage || userLocale || getBrowserLanguage(),
    return getLanguage(
      userLanguage || getBrowserLanguage(),
    );

  }, [userLocale, userLanguage]);

  document.documentElement.lang = language;

  const translate = useCallback(
    (
      key: string,
      keysToBeReplaced?: Record<string, React.ReactElement | string | number>,
      tempLang?: KnownLanguages,
    ): string => {
      const langToUse = (tempLang && getLanguage(tempLang)) || language;

      const mainDict = languages[langToUse];
      const fallbackDic = languages[getFallbackLanguage(langToUse)];

      const hasFallback = Object.keys(fallbackDic).length > 0;

      const replaceTranslation = (oldTranslation: string) => {
        let newTranslation = oldTranslation;
        if (keysToBeReplaced && Object.keys(keysToBeReplaced).length) {
          Object.keys(keysToBeReplaced).forEach(keyToBeReplaced => {
            const regex = new RegExp(keyToBeReplaced, 'g');
            const html = keysToBeReplaced[keyToBeReplaced];

            newTranslation = newTranslation.replace(
              regex,
              html
                ? typeof html === 'string' || typeof html === 'number'
                  ? html.toString()
                  : ReactDOMServer.renderToString(html)
                : '',
            );
          });
        }

        return newTranslation;
      };

      if (mainDict && isKeyof(key, mainDict) && mainDict[key]) {
        return replaceTranslation(mainDict[key]);
      } else if (
        hasFallback &&
        fallbackDic &&
        isKeyof(key, fallbackDic) &&
        fallbackDic[key]
      ) {
        return replaceTranslation(fallbackDic[key]);
      } else {
        return isDev || isLocalhost
          ? `__${replaceTranslation(key)}__`
          : replaceTranslation(key);
      }
    },
    [language],
  );

  return [translate, language] as const;
};

export type TranslateType = ReturnType<typeof useTranslation>[0];

export const replaceSubstringsWithTranslation = (
  str: string,
  substrings: string[],
  t: TranslateType,
) => {
  const inString = substrings.filter(substring => str.includes(substring));

  return inString.reduce((replacedString, currentSubstring) => {
    return replacedString.replace(
      new RegExp(currentSubstring, 'g'),
      t(currentSubstring),
    );
  }, str);
};
