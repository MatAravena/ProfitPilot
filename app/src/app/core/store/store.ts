import { configureStore } from '@reduxjs/toolkit'
import { authReducer } from '@core/slices/authSlice'
import { userReducer } from '@core/slices/userSlice'

export const store = () => {
  return configureStore({
    reducer: { 
      auth: authReducer,
      user: userReducer,
      // middleware: (getDefaultMiddleware) =>
      //   getDefaultMiddleware({ serializableCheck: false }),
    }
  })
}

// Infer the type of store
export type AppStore = ReturnType<typeof store>

// Infer the `RootState` and `AppDispatch` types from the store itself
export type RootState = ReturnType<AppStore['getState']>
export type AppDispatch = AppStore['dispatch']



// export type RootState = ReturnType<typeof store.getState>;
// export type AppDispatch = typeof store.dispatch;

// export const useAppDispatch = () => useDispatch<AppDispatch>();
// export const useAppSelector: TypedUseSelectorHook<RootState> = useSelector;
