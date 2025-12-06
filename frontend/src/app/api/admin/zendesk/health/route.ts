import { 
  validateAdminAccess, 
  getAdminConfig, 
  callUpstream 
} from '../_shared/route-helpers';

export async function GET() {
  const authError = await validateAdminAccess();
  if (authError) {
    return authError;
  }

  const configResult = getAdminConfig();
  if (configResult instanceof Response) {
    return configResult;
  }

  return callUpstream(
    '/api/v1/integrations/zendesk/admin/health',
    configResult
  );
}
