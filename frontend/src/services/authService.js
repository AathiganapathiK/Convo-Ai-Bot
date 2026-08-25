const API = process.env.REACT_APP_API_BASE_URL || "";
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

    let data = null;
    const contentType = response.headers.get("content-type");
    if (contentType && contentType.includes("application/json")) {
        try {
            data = await response.json();
        } catch (e) {
            console.error("Failed to parse JSON response:", e);
        }
    }

    if (!response.ok) {
        const errorDetail = data && data.detail ? data.detail : `Error ${response.status}: ${response.statusText || "Login failed"}`;
        throw new Error(errorDetail);
    }

    if (!data) {
        throw new Error("Invalid server response format");
    }

    return data;
}

export function saveToken(token) {
    localStorage.setItem("access_token", token);
}

export function getToken() {
    return localStorage.getItem("access_token");
}

export function logout() {
    localStorage.removeItem("access_token");
    localStorage.removeItem("selectedSessionId");
    localStorage.removeItem("userInfo");
}