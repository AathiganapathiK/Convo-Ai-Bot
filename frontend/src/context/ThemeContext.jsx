import React, { createContext, useState, useEffect } from "react";

const ThemeContext = createContext();

export const ThemeProvider = ({ children }) => {
  const [themeMode, setThemeModeState] = useState(() => {
    return localStorage.getItem("theme-mode") || "system";
  });

  // Calculate resolvedTheme immediately on startup
  const [resolvedTheme, setResolvedTheme] = useState(() => {
    const savedMode = localStorage.getItem("theme-mode") || "system";
    if (savedMode === "system") {
      return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
    }
    return savedMode;
  });

  const setThemeMode = (mode) => {
    setThemeModeState(mode);
    localStorage.setItem("theme-mode", mode);
  };

  // 1. Sync resolvedTheme with themeMode & OS theme
  useEffect(() => {
    const mediaQuery = window.matchMedia("(prefers-color-scheme: dark)");
    
    const updateTheme = () => {
      if (themeMode === "system") {
        setResolvedTheme(mediaQuery.matches ? "dark" : "light");
      } else {
        setResolvedTheme(themeMode);
      }
    };

    updateTheme();

    if (themeMode === "system") {
      // Modern event listener subscription
      mediaQuery.addEventListener("change", updateTheme);
      return () => {
        mediaQuery.removeEventListener("change", updateTheme);
      };
    }
  }, [themeMode]);

  // 2. Apply theme classes to document element and body
  useEffect(() => {
    const root = document.documentElement;
    const body = document.body;
    
    root.classList.remove("light-theme", "dark-theme");
    body.classList.remove("light-theme", "dark-theme");
    
    root.classList.add(`${resolvedTheme}-theme`);
    body.classList.add(`${resolvedTheme}-theme`);
  }, [resolvedTheme]);

  return (
    <ThemeContext.Provider value={{ themeMode, setThemeMode, resolvedTheme }}>
      {children}
    </ThemeContext.Provider>
  );
};

export default ThemeContext;
