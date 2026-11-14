/** Interpreta só a REFERÊNCIA, nunca consulta URLs informadas pelo usuário.
 * Na Nuvemshop 'number' (#14111) != 'id' da API (/admin/orders/2120958234).
 */
export type OrderReference={kind:"number"|"id";value:string;source:"label"|"link"|"number"|"internal"};

const valid=(text:string)=>/^[1-9][0-9]{0,17}$/.test(text);
const isOfficialHost=(host:string)=>
  /(^|\.)(lojavirtualnuvem\.com\.br|nuvemshop\.com\.br|nuvemshop\.com|tiendanube\.com)$/.test(host);

export function parseOrderReference(raw:string,internalId=false):OrderReference|null{
  const text=raw.trim();
  if(!text||text.length>500)return null;
  const label=/^#\s*([0-9]+)$/.exec(text);
  if(label&&valid(label[1]))return {kind:"number",value:label[1],source:"label"};
  if(/^https?:\/\//i.test(text)){
    try{
      const url=new URL(text);
      if(url.protocol!=="https:"||url.username||url.password||
         !isOfficialHost(url.hostname.toLowerCase()))return null;
      const match=/^\/admin\/orders\/([1-9][0-9]{0,17})\/?$/.exec(url.pathname);
      if(!match)return null;
      return {kind:"id",value:match[1],source:"link"};
    }catch{return null;}
  }
  if(valid(text)){
    return {kind:internalId?"id":"number",value:text,source:internalId?"internal":"number"};
  }
  return null;
}
