/* App do clube (PWA): manifest com nome e cores da loja, service worker
   mínimo e o convite de instalação. Importado cedo pelo main.tsx para não
   perder o evento beforeinstallprompt do Android/Chrome. */

type InstallPrompt = Event & {prompt:()=>Promise<void>;userChoice:Promise<{outcome:"accepted"|"dismissed"}>};

let deferred:InstallPrompt|null = null;
const listeners = new Set<()=>void>();
const notify = () => listeners.forEach(fn=>fn());

if(typeof window!=="undefined"){
  window.addEventListener("beforeinstallprompt",event=>{
    event.preventDefault();
    deferred = event as InstallPrompt;
    notify();
  });
  window.addEventListener("appinstalled",()=>{deferred=null;notify();});
}

export type InstallState = "installed"|"ready"|"ios"|"unsupported";

export function installState():InstallState{
  const standalone = window.matchMedia?.("(display-mode: standalone)").matches
    || (navigator as Navigator & {standalone?:boolean}).standalone === true;
  if(standalone) return "installed";
  if(deferred) return "ready";
  const ua = navigator.userAgent;
  if(/iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints>1)) return "ios";
  return "unsupported";
}

export function onInstallChange(fn:()=>void){
  listeners.add(fn);
  return ()=>{listeners.delete(fn);};
}

export async function promptInstall():Promise<boolean>{
  if(!deferred) return false;
  const event = deferred;
  deferred = null;
  await event.prompt();
  const choice = await event.userChoice;
  notify();
  return choice.outcome==="accepted";
}

/** Aponta o manifest e a cor do navegador para o clube da loja e registra o service worker. */
export function setupClubApp(slug:string, color:string){
  if(!slug) return;
  const href = "/api/v1/public/clubs/"+encodeURIComponent(slug)+"/manifest.webmanifest";
  let link = document.querySelector<HTMLLinkElement>('link[rel="manifest"]');
  if(!link){link=document.createElement("link");link.rel="manifest";document.head.appendChild(link);}
  if(link.getAttribute("href")!==href) link.setAttribute("href",href);
  if(!document.querySelector('meta[name="theme-color"]')){
    const meta=document.createElement("meta");meta.name="theme-color";document.head.appendChild(meta);
  }
  document.querySelectorAll<HTMLMetaElement>('meta[name="theme-color"]').forEach(meta=>meta.setAttribute("content",color));
  let apple = document.querySelector<HTMLLinkElement>('link[rel="apple-touch-icon"]');
  if(!apple){apple=document.createElement("link");apple.rel="apple-touch-icon";document.head.appendChild(apple);}
  apple.href = "/club-icon-192.png";
  if("serviceWorker" in navigator && window.isSecureContext){
    navigator.serviceWorker.register("/clube-sw.js",{scope:"/clube/"}).catch(()=>undefined);
  }
}
