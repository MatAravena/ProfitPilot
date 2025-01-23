"use client";

import { useContext, useState } from "react";
import AuthContext from "../context/authContext";
import axios from "axios";

const Login = () => {
    const login = useContext(AuthContext)?.login;
    const [username, setUsername] = useState('');
    const [password, setPassword] = useState('');
    const [registerUsername, setRegisterUsername] = useState('');
    const [registerPassword, setRegisterPassword] = useState('');

    // const handleSubmit = (e:FormEventHandler<HTMLFormElement>) => {
    //     e.preventDefault();
    const handleSubmit = async () => {
        if (login)
            await login(username, password)
    };

    // const handleRegister = async (e:FormEventHandler<HTMLFormElement>) => {
    //     e.preventDefault();
    const handleRegister = async () => {
      try {
         await axios.post('http://localhost:8000/auth', {
          username: registerUsername,
          password: registerPassword,
        });

        if (login)
            await login(registerUsername, registerPassword);

      } catch(error) {
        console.error('Failed to register user:', error);
    }
  }

    return (
        <div className="container">
            <h2>Login</h2>
            <form onSubmit={handleSubmit}>
                <div className="mb-3">
                <label htmlFor="username" className="form-label">Username</label>
                <input type="text" className="form-control" id="username" value={username} onChange={(e) => setUsername(e.target.value)} required />
                </div>
                <div className="mb-3">
                <label htmlFor="password" className="form-label">Password</label>
                <input type="password" className="form-control" id="password" value={password} onChange={(e) => setPassword(e.target.value)} required />
                </div>
                <button type="submit" className="btn btn-primary">Login</button>
            </form>

            <h2 className='mt-5'>Register</h2>
            <form onSubmit={handleRegister}>
                <div className="mb-3">
                <label htmlFor="registerUsername" className="form-label">Username</label>
                <input
                    type="text"
                    className="form-control"
                    id="registerUsername"
                    value={registerUsername}
                    onChange={(e) => setRegisterUsername(e.target.value)}
                    required
                />
                </div>
                <div className="mb-3">
                <label htmlFor="registerPassword" className="form-label">Password</label>
                <input
                    type="password"
                    className="form-control"
                    id="registerPassword"
                    value={registerPassword}
                    onChange={(e) => setRegisterPassword(e.target.value)}
                    required
                />
                </div>
                <button type="submit" className="btn btn-primary">Register</button>
            </form>
        </div>
      );
};

export default Login;
