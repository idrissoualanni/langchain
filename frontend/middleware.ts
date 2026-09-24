// Mission Identité — proxy Clerk pour domaine *.vercel.app.
//
// Sur un domaine Vercel on ne peut pas créer le sous-domaine
// clerk.<domain> ( Vercel contrôle le DNS ), donc Clerk est servi
// via le proxy app-origin /__clerk. Mais ce proxy n'est pas magique :
// en Next.js c'est @clerk/nextjs qui l'installe via clerkMiddleware.
// Ici c'est une SPA Vite — on l'écrit à la main.
//
// Ce edge function intercepte /__clerk/* et relaye vers le Frontend
// API Clerk ( clerk.<domain>, résolu via CNAME côté infra Clerk ).
export const config = {
  matcher: ['/__clerk/:path*'],
};

export default async function handler(req: Request): Promise<Response> {
  const url = new URL(req.url);

  // La publishable key contient le FAPI : pk_live_<base64(clerk.domain)>
  const pk = process.env.VITE_CLERK_PUBLISHABLE_KEY ?? '';
  const fapiDomain = pk.replace(/^pk_(live|test)_/, '').replace(/\$$/, '');

  if (!fapiDomain) {
    return new Response('VITE_CLERK_PUBLISHABLE_KEY missing', { status: 500 });
  }

  // On relaye vers le FAPI Clerk ( hostname du domaine enregistré ).
  const target = new URL(req.url);
  target.hostname = fapiDomain;
  target.pathname = url.pathname.replace(/^\/__clerk/, '');
  target.search = url.search;

  const headers = new Headers(req.headers);
  headers.set('host', fapiDomain);

  try {
    const upstream = await fetch(target.toString(), {
      method: req.method,
      headers,
      body: req.method === 'GET' || req.method === 'HEAD' ? undefined : req.body,
      redirect: 'manual',
    });

    const respHeaders = new Headers(upstream.headers);
    // Le FAPI répond avec des en-têtes CORS pour son domaine d'origine ;
    // on les retire pour que le navigateur revalide contre le nôtre.
    respHeaders.delete('access-control-allow-origin');
    respHeaders.append('access-control-allow-origin', url.origin);
    respHeaders.append('access-control-allow-credentials', 'true');

    return new Response(upstream.body, {
      status: upstream.status,
      statusText: upstream.statusText,
      headers: respHeaders,
    });
  } catch (e) {
    return new Response(`clerk proxy error: ${(e as Error).message}`, {
      status: 502,
    });
  }
}
