import { ReactNode } from "react";
import { User } from "./general";

export interface AuthContextType {
    user: User | undefined; 
    login: (username: string, password: string) => Promise<void>;
    logout: () => void;
}

export interface AuthProviderProps {
    children: ReactNode;
}