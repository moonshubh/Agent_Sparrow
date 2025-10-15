export function requireAdminApiConfig(): { apiBase: string; token: string } {
  const apiBase = process.env.API_BASE;
  const token = process.env.INTERNAL_API_TOKEN;

  if (!apiBase || !token) {
    throw new Error("server_config_missing");
  }

  return { apiBase, token };
}

export const __testing__ = { requireAdminApiConfig };
