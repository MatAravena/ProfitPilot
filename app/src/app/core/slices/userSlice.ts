// Slice as “a collection of Redux reducer logic and actions for a single feature

import { User } from "@app//types/general";
import { createSlice } from "@reduxjs/toolkit";
import type { PayloadAction } from "@reduxjs/toolkit";

const defaultUser: User = {
  id: 0,
};

export const userSlice = createSlice({
  name: "user",
  initialState: {...defaultUser},
  reducers: {
    setUserState: (state, action: PayloadAction<User>) => {
      state.user = { ...action.payload };
    },
  },
});

export const { setUserState } = userSlice.actions;
export const userReducer = userSlice.reducer;

