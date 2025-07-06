import { InitialState } from "@store/initialState";

export function userLanguageSelector(state: InitialState) {
  return state.user.language;
}

export function userLocaleSelector(state: InitialState) {
  return state.user.login?.login;
}
