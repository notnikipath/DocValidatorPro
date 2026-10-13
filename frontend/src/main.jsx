import { AppFrame } from "./AppFrame";
import React from "react";
import ReactDOM from "react-dom/client";

import { DashboardPage } from "./pages/DashboardPage";
import "./styles.css";

ReactDOM.createRoot(document.getElementById("root")).render(
  <React.StrictMode>
    <AppFrame><DashboardPage /></AppFrame>
  </React.StrictMode>
);
