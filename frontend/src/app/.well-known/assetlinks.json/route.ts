import { androidAssetLinks } from '../appLinkConfig';

export const dynamic = 'force-dynamic';

export async function GET() {
  return Response.json(androidAssetLinks(), {
    headers: {
      'content-type': 'application/json',
      'cache-control': 'public, max-age=3600',
    },
  });
}
