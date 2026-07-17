import type { Preview } from "@storybook/react-vite";
import { initialize, mswLoader } from "msw-storybook-addon";
import "../src/styles/tokens.css";
import "../src/styles/global.css";

initialize({ onUnhandledRequest: "bypass" });

const preview: Preview = {
  loaders: [mswLoader],
  parameters: {
    a11y: { test: "error" },
    layout: "padded",
  },
};

export default preview;
