import { de } from './de';
import { en } from './en';
import { es } from './es';

export const languages = {
  de,
  en,
  es,
} as const;

export type KnownLanguages = keyof typeof languages;
export const languageKeys = Object.keys(languages) as KnownLanguages[];

export const isLanguage = (lang: string): lang is KnownLanguages => {
  return languageKeys.includes(lang as KnownLanguages);
};

export const getBrowserLanguage = () => {
  const lang = navigator.language;

  // if (lang === 'en-CA') return 'en_CA';
  // if (lang === 'fr-CA') return 'fr_CA';

  const trimmedLang = lang.substring(0, 2);
  if (isLanguage(trimmedLang)) return trimmedLang;

  return 'de';
};

export const getFallbackLanguage = (lang: KnownLanguages) => {
  if (lang.includes('en') && lang !== 'en') {
    return 'en';
  }

  if (lang.includes('de') || lang.includes('en')) {
    return 'de';
  }

  return 'en';
};

export default languages;
