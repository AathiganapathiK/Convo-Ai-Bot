const API =
  process.env.REACT_APP_API_BASE_URL ||
  "http://127.0.0.1:8000";

export const getRoles = async (token) => {

  const response = await fetch(
    `${API}/roles`,
    {
      headers: {
        Authorization: `Bearer ${token}`
      }
    }
  );

  return response.json();
};

export const getPermissions = async (token) => {

  const response = await fetch(
    `${API}/permissions`,
    {
      headers: {
        Authorization: `Bearer ${token}`
      }
    }
  );

  return response.json();
};

export const createRole = async (
  token,
  payload
) => {

  const response = await fetch(
    `${API}/roles`,
    {
      method: "POST",
      headers: {
        Authorization: `Bearer ${token}`,
        "Content-Type": "application/json"
      },
      body: JSON.stringify(payload)
    }
  );

  return response.json();
};

export const deleteRole = async (
  token,
  roleId
) => {

  const response = await fetch(
    `${API}/roles/${roleId}`,
    {
      method: "DELETE",
      headers: {
        Authorization: `Bearer ${token}`
      }
    }
  );

  return response.json();
};

export const getRolePermissions =
  async (
    token,
    roleId
  ) => {

    const response =
      await fetch(
        `${API}/roles/${roleId}/permissions`,
        {
          headers: {
            Authorization:
              `Bearer ${token}`
          }
        }
      );

    return response.json();
};