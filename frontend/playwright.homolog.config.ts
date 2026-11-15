/** PR24: somente homologação HTTPS real; NUNCA usa o preview local ou mocks. */
import {defineConfig} from "@playwright/test";

const baseURL=process.env.FIDELIZA_HOMOLOG_BASE_URL;
if(baseURL!=="https://fideliza-homolog.optarys.com.br"){
  throw new Error("FIDELIZA_HOMOLOG_BASE_URL deve ser o domínio exato de homologação.");
}
export default defineConfig({
  testDir:"./homolog",
  outputDir:"./test-results-homolog",
  reporter:[["list"]],
  use:{
    baseURL,
    browserName:"chromium",
    trace:"off",
    screenshot:"off",
    video:"off",
    ignoreHTTPSErrors:false,
  },
  retries:0,
  workers:1,
  timeout:90000,
});
