import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import "../../src/a5s/core/webchat/app.css";  // the look every page of a5s shares
import "./studio.css";
import { App } from "./App";

document.body.classList.add("app");
createRoot(document.getElementById("root")!).render(<StrictMode><App /></StrictMode>);
