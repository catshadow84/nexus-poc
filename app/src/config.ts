const apiUrl = process.env.EXPO_PUBLIC_API_URL;

if (!apiUrl) {
  throw new Error(
    'EXPO_PUBLIC_API_URL is not set. Copy .env.example to .env.local and set it to your backend URL.',
  );
}

export const API_URL: string = apiUrl.replace(/\/$/, '');
export const WS_URL: string = API_URL.replace(/^http/, 'ws') + '/ws';