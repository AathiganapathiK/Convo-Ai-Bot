const API =
  process.env.REACT_APP_API_BASE_URL ||
  "http://127.0.0.1:8000";

export const getUserRoles = async (
  token,
  employeeId
) => {

  const response =
    await fetch(
      `${API}/user-roles/${employeeId}/names`,
      {
        headers: {
          Authorization:
            `Bearer ${token}`
        }
      }
    );

  return response.json();
};

export const assignRole =
  async (
    token,
    employee_id,
    role_id
  ) => {

    const response =
      await fetch(
        `${API}/user-roles`,
        {
          method: "POST",
          headers: {
            Authorization:
              `Bearer ${token}`,
            "Content-Type":
              "application/json"
          },
          body: JSON.stringify({
            employee_id,
            role_id
          })
        }
      );

    return response.json();
};