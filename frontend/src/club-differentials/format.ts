/* Formatação pt-BR idêntica a backend/apps/loyalty/engine/formatting.py. */

const thousands = (value: number) =>
  Math.abs(Math.trunc(value)).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ".");

export function brl(cents: number): string {
  if (!Number.isInteger(cents)) throw new Error("Centavos devem ser inteiros.");
  const sign = cents < 0 ? "-" : "";
  const abs = Math.abs(cents);
  return `${sign}R$ ${thousands(Math.floor(abs / 100))},${String(abs % 100).padStart(2, "0")}`;
}

export function points(amount: number, short = false): string {
  if (!Number.isInteger(amount)) throw new Error("Pontos devem ser inteiros.");
  const text = (amount < 0 ? "-" : "") + thousands(amount);
  if (short) return Math.abs(amount) === 1 ? `${text} pt` : `${text} pts`;
  return Math.abs(amount) === 1 ? `${text} ponto` : `${text} pontos`;
}

export function days(amount: number): string {
  return amount === 1 ? "1 dia" : `${thousands(amount)} dias`;
}

export function dateBR(iso: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) throw new Error("Data inválida.");
  return `${match[3]}/${match[2]}/${match[1]}`;
}

export function percent(value: number, digits = 1): string {
  return (value * 100).toFixed(digits).replace(".", ",") + "%";
}

export function ratio(value: number): string {
  return value.toFixed(2).replace(".", ",") + "×";
}

export function whatsappShareUrl(storeName: string, clubUrl: string): string {
  const text = `Conheça o clube da ${storeName}: suas compras viram pontos e recompensas. ${clubUrl}`;
  return "https://wa.me/?text=" + encodeURIComponent(text);
}
