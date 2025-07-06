import React from "react";

export type WithChildren<T extends {}> = T & { children?: React.ReactNode };
export type Modify<T, R> = Omit<T, keyof R> & R;
export const genericMemo: <T>(component: T) => T = React.memo;

export type FarmSettingsValueType =
  | number
  | string
  | number[]
  | string[]
  | Record<string, any>
  | Record<string, any>[];

const saneFileName = (name: string) =>
  name
    .replace(/Ä/g, 'Ae')
    .replace(/Ö/g, 'Oe')
    .replace(/Ü/g, 'Ue')
    .replace(/ä/g, 'ae')
    .replace(/ö/g, 'oe')
    .replace(/ü/g, 'ue')
    .replace(/ß/g, 'ss')
    .replace(/\s+/g, '-')
    .replace(/[^a-zA-Z0-9._-]/g, '');

export { saneFileName };

export const isElectron = navigator.userAgent.includes('Electron');

export const deepCopy = <T = any>(element: T): T => {
  return JSON.parse(JSON.stringify(element));
};

export const convertDMFM = (value: number | string, fm?: number | string) => {
  const localFM = fm ? fm : 1;

  const floatValue = parseFloat(value.toString());
  const floatFM = parseFloat(localFM.toString());

  if (isNaN(floatValue) || isNaN(floatFM)) return value;

  return floatValue / floatFM;
};

export const sortFunction = (
  a: any,
  b: any,
  order: 'ASC' | 'DESC',
  key: string,
) => {
  if (order === 'ASC') {
    return a[key] - b[key];
  }

  return b[key] - a[key];
};

export const areNumbersEqual = (
  value1: number,
  value2: number,
  tolerance: number,
) => {
  return Number(Math.abs(value1 - value2).toFixed(10)) <= tolerance;
};

const alwaysStrings = ['name', 'description'];

export const convertToRealTypes = <T>(obj: any): T => {
  Object.keys(obj).forEach(key => {
    if (typeof obj[key] !== 'string') return;

    if (
      !alwaysStrings.includes(key) &&
      !isNaN(Number(obj[key])) &&
      !isNaN(parseFloat(obj[key])) &&
      obj[key] !== ''
    ) {
      obj[key] = Number(obj[key]);
    }

    if (obj[key] === 'false') {
      obj[key] = false;
    }

    if (obj[key] === 'true') {
      obj[key] = true;
    }
  });

  return obj as T;
};

export const parseJSONString = (str: string) => {
  let returnValue = str;
  let counter = 0;
  while (typeof returnValue === 'string' && counter < 5) {
    counter++;
    returnValue = JSON.parse(returnValue);
  }
  return returnValue as FarmSettingsValueType;
};

export const getTextFromHtml = (stringWithHtmlTags: string) => {
  return stringWithHtmlTags.replace(/<[^>]+>/g, '');
};

//spliting array into subarrays with specified chunk size
export const spliceArrayIntoChunks = (array: any, chunkSize: number) => {
  const newArray = [];
  while (array.length > 0) {
    newArray.push(array.splice(0, chunkSize));
  }
  return newArray;
};

const isObjectObject = (thing: unknown): thing is object =>
  isObject(thing) &&
  Object.prototype.toString.call(thing) === '[object Object]';

export const isPlainObject = (thing: unknown): thing is Record<string, any> => {
  if (!isObjectObject(thing)) {
    return false;
  }

  // If has modified constructor
  const ctor = thing.constructor;
  if (typeof ctor !== 'function') {
    return false;
  }

  // If has modified prototype
  const prot = ctor.prototype;
  if (!isObjectObject(prot)) {
    return false;
  }

  // If constructor does not have an Object-specific method
  // eslint-disable-next-line no-prototype-builtins
  if (!prot.hasOwnProperty('isPrototypeOf')) {
    return false;
  }

  // Most likely a plain Object
  return true;
};

export const isKeyof = <T extends Record<string | number | symbol, unknown>>(
  key: any,
  object: T,
): key is keyof T => key in object;

export const hasKey = <O extends object>(
  obj: O,
  key: keyof any,
): key is keyof O => {
  return key in obj;
};

// checks if all objects passed to the function have the exact same keys
export const haveSameKeys = (...objects: any[]) => {
  const allKeys = objects.reduce(
    (keys, object) => keys.concat(Object.keys(object)),
    [],
  );
  const union = new Set(allKeys);
  return objects.every(object => union.size === Object.keys(object).length);
};

// see: https://www.typescriptlang.org/docs/handbook/advanced-types.html#exhaustiveness-checking
export const assertNever = (arg: never): never => {
  throw new Error(`Unexpected object: ${arg}`);
};

// TODO: find a better way to decide if we are in development or production mode
// export const isDev = window && window.location.hostname.includes('localhost');
export const isDev = typeof window !== "undefined" && window.location.hostname.includes("localhost");

export const isLocalhost =
  typeof window !== "undefined" &&
  (window.location.hostname === 'localhost' ||
    window.location.hostname.startsWith('127.'));

export const isPreprod =
  typeof window !== "undefined" && window.location.hostname.includes('preprod.fodjan');
export const isStaging =
  typeof window !== "undefined" && window.location.hostname.includes('staging.fodjan');

export const capitalize = (str: string) =>
  str.charAt(0).toUpperCase() + str.slice(1);

export const isObjectEmpty = (obj: Record<string, any>) => {
  return obj && Object.keys(obj).length === 0 && obj.constructor === Object;
};

export const stripValue = (
  value: number | string,
  t: (str: string) => string,
) => {
  const numberValue = Number(value);

  if (numberValue >= 10000 || numberValue <= -10000) {
    return Math.round(numberValue / 1000) + t('Tsd');
  }

  return value;
};

export const replaceBackslashNWithBR = (str: string) => {
  return str.replace(/\n/g, '<br/>');
};

export const isValueEmpty = (
  n: number | string | undefined | boolean | null | unknown,
) => {
  return (
    n === null ||
    n === undefined ||
    n === -1e35 ||
    n === -1.0e35 ||
    n?.toString() === '-1e35' ||
    n?.toString() === '-1e+35' ||
    Number(n) < -99999999999 ||
    n === '' ||
    n === false
  );
};

export const getAnonymousUrl = (url: string) => {
  // remove last slash from each url
  url = url.replace(/\/$/, '');
  // if url ends with farm
  url = url.replace(/[0-9]+-[^/]*$/, '42-myfarm');
  // if url has farm in the middle
  url = url.replace(/[0-9]+-[^/]*\//, '42-myfarm/');
  // replace all IDs in the url with 42
  url = url.replace(/\/[0-9]+\/*$/, '/42');
  return url;
};

export const sleep = (time: number) => {
  return new Promise(resolve => setTimeout(resolve, time));
};

export const clamp = (value: number, range1: number, range2: number) => {
  const low = range1 < range2 ? range1 : range2;
  const high = range1 > range2 ? range1 : range2;

  return Math.min(Math.max(value, low), high);
};

export const isNotEmpty = <T extends Record<string, unknown>>(
  obj: T | {},
): obj is T => {
  return !(
    obj &&
    Object.keys(obj).length === 0 &&
    Object.getPrototypeOf(obj) === Object.prototype
  );
};

export const removeKeysFromObject = <
  T extends Record<string, unknown | undefined>,
>(
  obj: T,
  keys: string[],
) => {
  const resultObj = deepCopy(obj);

  for (const k of keys) {
    if (resultObj[k] === undefined) continue;
    delete resultObj[k];
  }

  return resultObj;
};

export const arraySwitchPosition = <T extends unknown>(
  array: T[],
  fromPosition: number,
  toPosition: number,
) => {
  const newArray = [...array];
  const element = newArray.splice(fromPosition, 1)[0];
  newArray.splice(toPosition, 0, element);

  return newArray;
};

// export const hasFeatureFlag = (
//   selectFarm: SelectFarm | null,
//   flag: Features,
// ) => {
//   const featureFlags =
//     selectFarm?.jwt_data?.fj_fef ?? selectFarm?.feature_flags;

//   if (featureFlags === undefined) return false;

//   return hasBit(featureFlags, flag);
// };

// export const getMatomoSiteId = () => {
//   if (isLocalhost) {
//     return null;
//   }
//   if (isDev) {
//     return MatomoSiteId.DEV;
//   }
//   if (isStaging) {
//     return MatomoSiteId.STAGING;
//   }
//   if (isPreprod) {
//     return MatomoSiteId.PREPROD;
//   }
//   return MatomoSiteId.PROD;
// };

export const isIframe = (
  iframe: HTMLElement | null,
): iframe is HTMLIFrameElement => {
  return iframe?.tagName === 'IFRAME';
};

export const hasID = (
  maybeWithID: any,
): maybeWithID is { id: string | number } => {
  return maybeWithID?.id !== undefined;
};

export const isObject = (thing: unknown) =>
    thing !== null &&
    thing !== undefined &&
    typeof thing === 'object' &&
    Array.isArray(thing) === false;

export const hasBit = (value: number, bit: number) => {
    return (value & bit) === bit;
};