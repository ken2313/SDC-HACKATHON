import { request } from "./client.js";

// Sign-in for the demo workspace. The backend checks the email and password and returns a
// signed token. The password is never stored in this website's code.
export const authApi = {
  login: (email, password) => request("/auth/login", { method: "POST", body: { email, password } }),
  session: () => request("/auth/session"),
  logout: () => request("/auth/logout", { method: "POST" }),
};
