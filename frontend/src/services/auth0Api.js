import { useAuth0 } from "@auth0/auth0-react";

export const getToken = async (getAccessTokenSilently) => {
  return await getAccessTokenSilently();
};