const API =
  process.env.REACT_APP_API_BASE_URL ||
  "http://127.0.0.1:8000";

export const getCompanyInfo = async (token) => {
  const response = await fetch(
    `${API}/company`,
    {
      headers: {
        Authorization: `Bearer ${token}`
      }
    }
  );

  return response.json();
};

export const getTenantConfig = async (token) => {
  const response = await fetch(
    `${API}/tenant-config`,
    {
      headers: {
        Authorization: `Bearer ${token}`
      }
    }
  );

  return response.json();
};

export const updateTenantConfig = async (
  token,
  payload
) => {

  const response = await fetch(
    `${API}/tenant-config`,
    {
      method: "PUT",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    }
  );

  return response.json();
};