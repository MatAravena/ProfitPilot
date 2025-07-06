
export interface User {
    id: number;
    username?: string;
    password?: string;
    name?: string;
    last_name?: string;
    phone?: string;
    email?: string;
    createdAt?: Date;
    birthDate?: string;
    roles?: string[];
    token?: string;
};
