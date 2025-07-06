import { KnownLanguages } from "@hooks/languages";

export interface Login {
  language: any;
  login: null | Login;
  privileges: number[];
  jwt: string;
  last_login: string;
  last_login_iso: string;
  select_country: string;
  sh_admin: boolean;
  state: string;
  // user: User;
  // user_license: string;
  userkey: string;
}

export interface UserState {
  language: null | KnownLanguages;
  login: null | Login;
  privileges: number[];
  // language: null | KnownLanguages;
  // credentials: null | { email: string; password: string };
  // notifications: Notification[];
  // changedLicenses: ChangedLicense[];
  // activeLicenses: ActiveLicense[];
  // archivedFarms: ArchivedFarm[];
}

export interface InitialState {
  user: UserState;
  // farms: Record<string, FarmState>;
  meta: {
    currentRequests: { key: string; timestamp: number }[];
    activeMenuItems: string[];
    // proxyConf?: null | ProxyConf; // null indicating there was an issue getting the conf
    // syncPlugins: PluginSyncResult | null;
    shouldReloadPage: boolean;
    shouldReloadProxyConfig: boolean;
  };
  // temp: TempState;
  persist: {
    lastLoginPage: string;
    // globalInfo: null | GlobalInfoState;
    isOnline: boolean;
    lostConnection: boolean;
    daysWithoutBackend: number;
    // syncInfo: Record<string, SyncInfo | undefined>;
    restoreConnection: boolean;
    backendAvailable: boolean;
  };
}

const initialState: InitialState = {
  user: {
    login: null,
    privileges: [],
    language: null,
    // credentials: null,
    // notifications: [],
    // changedLicenses: [],
    // activeLicenses: [],
    // archivedFarms: [],
  },
  // temp: {
  //   // compoundFeed: defaultCompoundFeed,
  //   hds: {
  //     hdsAmsDraftLibrary: [],
  //     hdsAmsReportLibrary: [],
  //     hdsDraftLibrary: [],
  //     hdsReportLibrary: [],
  //   },
  //   // mix: defaultCompoundFeed,
  //   documentation: {
  //     currentFeedingstuffs: [],
  //   },
  //   powerfood23: {
  //     powerfood: null,
  //     feedmix: null,
  //   },
  //   dataCenter: [],
  //   stakeHolderDataCenter: [],
  // },
  meta: {
    currentRequests: [],
    activeMenuItems: [],
    // syncPlugins: {},
    shouldReloadPage: false,
    shouldReloadProxyConfig: false,
  },
  persist: {
    lastLoginPage: '/',
    // globalInfo: null,
    isOnline: true,
    lostConnection: false,
    daysWithoutBackend: 0,
    // syncInfo: {},
    restoreConnection: true,
    backendAvailable: true,
  },
};

export default initialState;
