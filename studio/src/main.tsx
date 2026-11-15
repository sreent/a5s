import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
// Ocean, the look every page of a5s shares, as a5s copies it from sreent/ocean (deploy/ocean.sh)
import "../../src/a5s/core/webchat/ocean/css/tokens.css";
import "../../src/a5s/core/webchat/ocean/css/components.css";
import "../../src/a5s/core/webchat/ocean/css/charts.css";
import "./studio.css";
import { App } from "./App";

document.body.classList.add("app");
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
