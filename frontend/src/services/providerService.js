const API =
  process.env.REACT_APP_API_BASE_URL ||
  "http://127.0.0.1:8000";

export const getProviders = async (
  token
) => {

  const response =
    await fetch(
      `${API}/providers`,
      {
        headers: {
          Authorization:
            `Bearer ${token}`
        }
      }
    );

  return response.json();
};

export const createProvider =
  async (
    token,
    payload
  ) => {

    const response =
      await fetch(
        `${API}/providers`,
        {
          method: "POST",
          headers: {
            Authorization:
              `Bearer ${token}`,
            "Content-Type":
              "application/json"
          },
          body:
            JSON.stringify(payload)
        }
      );

    return response.json();
};

export const getModels =
  async (
    token
  ) => {

    const response =
      await fetch(
        `${API}/models`,
        {
          headers: {
            Authorization:
              `Bearer ${token}`
          }
        }
      );

    return response.json();
};