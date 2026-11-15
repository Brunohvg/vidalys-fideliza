/** PR30 QA-only NubeSDK checkout protection. NOT a server-side guarantee.
 * Build with NubeSDK toolchain and install ONLY in a demo store through Partner Portal.
 * The token MUST originate from the verified member portal; shopper email alone
 * never verifies ownership. No DOM, no raw CPF, no OAuth or PSP secrets.
 */
import type { NubeSDK, NubeSDKState } from "@tiendanube/nube-sdk-types";

const ELIGIBILITY_URL = "https://YOUR-QA-APP.example/api/v1/public/coupons/check-eligibility/";
const SESSION_KEY = "vidalys_checkout_eligibility_token";
const CODE_PATTERN = /^VF[A-Za-z0-9_-]{8,78}$/;

export function App(nube: NubeSDK): void {
  nube.send("config:set", () => ({
    config: { has_cart_validation: true },
  }));
  let revision = 0;
  let hasOurFailure = false;
  const fail = () => {
    hasOurFailure = true;
    nube.send("cart:validate", () => ({
      cart: { validation: {
        status: "fail",
        reason: "Não foi possível confirmar o titular deste cupom. Aplique um cupom da sua própria conta.",
      }},
    }));
    nube.send("coupon:remove");
  };
  async function inspect(state: Readonly<NubeSDKState>): Promise<void> {
    const code = state.cart.coupon?.code;
    if (!code || !CODE_PATTERN.test(code)) {
      revision++;
      // Clear only our own failed validation after the coupon was removed.
      if (hasOurFailure) {
        hasOurFailure = false;
        nube.send("cart:validate", () => ({
          cart: { validation: { status: "success" } },
        }));
      }
      return;
    }
    const current = ++revision;
    nube.send("cart:validate", () => ({
      cart: { validation: { status: "pending" } },
    }));
    try {
      const token = await nube.getBrowserAPIs().asyncSessionStorage.getItem(SESSION_KEY);
      const email = state.customer?.contact.email;
      if (!token || !email) { if (current === revision) fail(); return; }
      const response = await fetch(ELIGIBILITY_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          store_id: state.store.id,
          code,
          email,
          identity_token: token,
        }),
      });
      const result: unknown = await response.json();
      const matched = response.ok && typeof result === "object" && result !== null
        && "eligible" in result && (result as { eligible: unknown }).eligible === true;
      if (current !== revision) return;
      if (!matched) { fail(); return; }
      hasOurFailure = false;
      nube.send("cart:validate", () => ({
        cart: { validation: { status: "success" } },
      }));
    } catch {
      if (current === revision) fail();
    }
  }
  nube.on("cart:update", inspect);
  nube.on("checkout:ready", inspect);
  nube.on("customer:update", inspect);
}
