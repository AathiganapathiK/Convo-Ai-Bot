const API = process.env.REACT_APP_API_BASE_URL || "/api";

export async function login(email, password) {
    const response = await fetch(`${API}/auth/login`, {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({
            email,
            password
        })
    });

    if (!response.ok) {
        const error = await response.json();
        throw new Error(error.detail || "Login failed");
    }

    return response.json();
}

export function saveToken(token) {
    localStorage.setItem("access_token", token);
}

export function getToken() {
    return localStorage.getItem("access_token");
}

export function logout() {
    localStorage.removeItem("access_token");
}