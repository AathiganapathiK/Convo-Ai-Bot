import React, { useState } from "react";
import { Form, Input, Button, Checkbox, Typography, Tooltip } from "antd";
import { LockOutlined, MailOutlined, SunOutlined, MoonOutlined, DesktopOutlined } from "@ant-design/icons";
import { Bot, ArrowRight, ShieldCheck, Sparkles, TrendingUp, MessageSquare, BarChart3, Database } from "lucide-react";
import { useTheme } from "../hooks/useTheme";

const { Title, Text } = Typography;

const LoginPage = ({ onLogin, loginForm, loginLoading }) => {
  const { themeMode, setThemeMode, resolvedTheme } = useTheme();
  const [rememberMe, setRememberMe] = useState(true);

  const isDark = resolvedTheme === "dark";

  return (
    <div
      style={{
        minHeight: "100vh",
        width: "100vw",
        display: "flex",
        background: "var(--bg-layout)",
        color: "var(--text-main)",
        position: "relative",
        overflowX: "hidden",
        fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif",
        transition: "background 0.3s ease, color 0.3s ease",
      }}
    >
      {/* Floating Theme Mode Selector (Top Right) */}
      <div
        style={{
          position: "absolute",
          top: "24px",
          right: "28px",
          zIndex: 100,
          display: "flex",
          alignItems: "center",
          gap: "4px",
          background: isDark ? "rgba(17, 24, 39, 0.8)" : "rgba(255, 255, 255, 0.9)",
          backdropFilter: "blur(8px)",
          padding: "4px",
          borderRadius: "10px",
          border: "1px solid var(--border-color)",
          boxShadow: isDark ? "0 4px 12px rgba(0, 0, 0, 0.3)" : "0 4px 12px rgba(0, 0, 0, 0.05)",
        }}
      >
        <Tooltip title="Light Theme">
          <Button
            type={themeMode === "light" ? "primary" : "text"}
            size="small"
            icon={<SunOutlined />}
            onClick={() => setThemeMode("light")}
            style={{
              borderRadius: "6px",
              color: themeMode === "light" ? "#ffffff" : "var(--text-muted)",
              background: themeMode === "light" ? "#4f46e5" : "transparent",
            }}
          />
        </Tooltip>
        <Tooltip title="Dark Theme">
          <Button
            type={themeMode === "dark" ? "primary" : "text"}
            size="small"
            icon={<MoonOutlined />}
            onClick={() => setThemeMode("dark")}
            style={{
              borderRadius: "6px",
              color: themeMode === "dark" ? "#ffffff" : "var(--text-muted)",
              background: themeMode === "dark" ? "#4f46e5" : "transparent",
            }}
          />
        </Tooltip>
        <Tooltip title="System Preference">
          <Button
            type={themeMode === "system" ? "primary" : "text"}
            size="small"
            icon={<DesktopOutlined />}
            onClick={() => setThemeMode("system")}
            style={{
              borderRadius: "6px",
              color: themeMode === "system" ? "#ffffff" : "var(--text-muted)",
              background: themeMode === "system" ? "#4f46e5" : "transparent",
            }}
          />
        </Tooltip>
      </div>

      {/* Main Container - Split Screen 55% / 45% */}
      <div
        style={{
          display: "flex",
          width: "100%",
          minHeight: "100vh",
          flexWrap: "wrap",
        }}
      >
        {/* LEFT SECTION (~55%): Brand Logo + Modern AI Business Illustration */}
        <div
          className="login-left-section"
          style={{
            flex: "1 1 55%",
            minWidth: "340px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "space-between",
            padding: "40px 48px",
            background: isDark
              ? "linear-gradient(135deg, #070a14 0%, #0f172a 60%, #1e1b4b 100%)"
              : "linear-gradient(135deg, #ffffff 0%, #f8fafc 60%, #eff6ff 100%)",
            borderRight: "1px solid var(--border-color)",
            position: "relative",
            boxSizing: "border-box",
          }}
        >
          {/* Upper-Left Branding / Logo */}
          <div style={{ display: "flex", alignItems: "center", gap: "12px" }}>
            <div
              style={{
                width: "40px",
                height: "40px",
                borderRadius: "10px",
                background: "linear-gradient(135deg, #4f46e5 0%, #6366f1 100%)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
                color: "#ffffff",
                boxShadow: "0 4px 12px rgba(79, 70, 229, 0.3)",
              }}
            >
              <Bot size={22} />
            </div>
            <div>
              <Title
                level={4}
                style={{
                  margin: 0,
                  fontSize: "18px",
                  fontWeight: 800,
                  letterSpacing: "-0.3px",
                  color: "var(--text-main)",
                }}
              >
                Convo AI
              </Title>
              <Text style={{ fontSize: "11px", color: "var(--text-muted)", letterSpacing: "0.5px", fontWeight: 600 }}>
                RETAIL INTELLIGENCE
              </Text>
            </div>
          </div>

          {/* Central AI Analytics Illustration */}
          <div
            style={{
              margin: "auto 0",
              display: "flex",
              flexDirection: "column",
              alignItems: "center",
              justifyContent: "center",
              padding: "20px 0",
            }}
          >
            {/* Custom Modern Vector SVG AI Business Illustration */}
            <div
              style={{
                width: "100%",
                maxWidth: "460px",
                height: "auto",
                position: "relative",
                marginBottom: "32px",
                filter: isDark ? "drop-shadow(0 12px 24px rgba(0,0,0,0.5))" : "drop-shadow(0 12px 24px rgba(99,102,241,0.12))",
              }}
            >
              <svg viewBox="0 0 500 360" fill="none" xmlns="http://www.w3.org/2000/svg" style={{ width: "100%", height: "100%" }}>
                {/* Background Grid Lines */}
                <pattern id="grid" width="30" height="30" patternUnits="userSpaceOnUse">
                  <path d="M 30 0 L 0 0 0 30" fill="none" stroke={isDark ? "rgba(255,255,255,0.04)" : "rgba(79,70,229,0.06)"} strokeWidth="1" />
                </pattern>
                <rect width="500" height="360" fill="url(#grid)" rx="16" />

                {/* Ambient Glow Orbs */}
                <circle cx="250" cy="180" r="120" fill={isDark ? "#4f46e5" : "#6366f1"} fillOpacity={isDark ? "0.12" : "0.08"} filter="blur(30px)" />
                <circle cx="380" cy="100" r="80" fill={isDark ? "#38bdf8" : "#3b82f6"} fillOpacity={isDark ? "0.1" : "0.07"} filter="blur(25px)" />

                {/* Central Main Analytics Dashboard Window Card */}
                <rect x="70" y="50" width="360" height="240" rx="16" fill={isDark ? "#1e293b" : "#ffffff"} stroke={isDark ? "#334155" : "#e2e8f0"} strokeWidth="1.5" />
                <rect x="70" y="50" width="360" height="36" rx="16" fill={isDark ? "#0f172a" : "#f8fafc"} />
                <circle cx="92" cy="68" r="4" fill="#ef4444" />
                <circle cx="106" cy="68" r="4" fill="#f59e0b" />
                <circle cx="120" cy="68" r="4" fill="#10b981" />
                <rect x="140" y="62" width="180" height="12" rx="6" fill={isDark ? "#334155" : "#e2e8f0"} fillOpacity="0.6" />

                {/* Vector Bar Chart */}
                <rect x="100" y="190" width="24" height="60" rx="4" fill="#818cf8" />
                <rect x="136" y="150" width="24" height="100" rx="4" fill="#4f46e5" />
                <rect x="172" y="120" width="24" height="130" rx="4" fill="#6366f1" />
                <rect x="208" y="170" width="24" height="80" rx="4" fill="#38bdf8" />
                <rect x="244" y="110" width="24" height="140" rx="4" fill="#4f46e5" />

                {/* Trend Curve Line */}
                <path d="M 112 185 Q 160 120 220 150 T 310 100" fill="none" stroke="#34d399" strokeWidth="3.5" strokeLinecap="round" />
                <circle cx="310" cy="100" r="6" fill="#34d399" stroke={isDark ? "#1e293b" : "#ffffff"} strokeWidth="2" />

                {/* AI Chat Bubble Floating Card (Right) */}
                <g transform="translate(290, 160)">
                  <rect width="160" height="90" rx="12" fill={isDark ? "#0f172a" : "#ffffff"} stroke={isDark ? "#475569" : "#cbd5e1"} strokeWidth="1.5" />
                  <rect x="16" y="16" width="128" height="10" rx="5" fill="#6366f1" />
                  <rect x="16" y="34" width="96" height="8" rx="4" fill={isDark ? "#334155" : "#e2e8f0"} />
                  <rect x="16" y="48" width="112" height="8" rx="4" fill={isDark ? "#334155" : "#e2e8f0"} />
                  <rect x="16" y="64" width="60" height="14" rx="7" fill="#10b981" fillOpacity="0.2" />
                  <text x="24" y="74" fill="#10b981" fontSize="9" fontWeight="bold">98.4% Accuracy</text>
                </g>

                {/* Floating Intelligence Badge (Left) */}
                <g transform="translate(40, 110)">
                  <rect width="130" height="44" rx="10" fill={isDark ? "#0f172a" : "#ffffff"} stroke="#818cf8" strokeWidth="1.5" />
                  <circle cx="22" cy="22" r="10" fill="#4f46e5" />
                  <path d="M 18 22 L 21 25 L 27 19" fill="none" stroke="#ffffff" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
                  <rect x="38" y="14" width="76" height="8" rx="4" fill={isDark ? "#f8fafc" : "#1e293b"} />
                  <rect x="38" y="26" width="50" height="6" rx="3" fill="#818cf8" />
                </g>
              </svg>
            </div>

            {/* Concise Supporting Heading */}
            <div style={{ textAlign: "center", maxWidth: "420px" }}>
              <Title
                level={3}
                style={{
                  margin: 0,
                  fontSize: "22px",
                  fontWeight: 700,
                  color: "var(--text-main)",
                  letterSpacing: "-0.3px",
                }}
              >
                AI-Powered Retail Analytics
              </Title>
              <Text
                style={{
                  fontSize: "13.5px",
                  color: "var(--text-muted)",
                  lineHeight: "1.6",
                  marginTop: "8px",
                  display: "block",
                }}
              >
                Real-time conversational queries, automated intent routing, and row-level security policy enforcement.
              </Text>
            </div>
          </div>

          {/* Bottom Compliance Micro Highlights */}
          <div
            style={{
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              gap: "24px",
              paddingTop: "16px",
              borderTop: "1px solid var(--border-color)",
            }}
          >
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <Sparkles size={14} style={{ color: "#6366f1" }} />
              <Text style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 500 }}>Smart NL2SQL</Text>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <TrendingUp size={14} style={{ color: "#10b981" }} />
              <Text style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 500 }}>Live BI Pipeline</Text>
            </div>
            <div style={{ display: "flex", alignItems: "center", gap: "6px" }}>
              <ShieldCheck size={14} style={{ color: "#38bdf8" }} />
              <Text style={{ fontSize: "12px", color: "var(--text-muted)", fontWeight: 500 }}>RLS Security</Text>
            </div>
          </div>
        </div>

        {/* RIGHT SECTION (~45%): Compact Clean Login Form (Reference Style) */}
        <div
          style={{
            flex: "1 1 45%",
            minWidth: "320px",
            display: "flex",
            flexDirection: "column",
            justifyContent: "center",
            alignItems: "center",
            padding: "40px 32px",
            background: "var(--bg-layout)",
            boxSizing: "border-box",
          }}
        >
          {/* Compact Form Wrapper (Max Width 400px - No Heavy Enclosed Card) */}
          <div
            style={{
              width: "100%",
              maxWidth: "400px",
            }}
          >
            {/* Header: "Welcome Back" */}
            <div style={{ marginBottom: "32px", textAlign: "left" }}>
              <Title
                level={2}
                style={{
                  margin: 0,
                  fontSize: "28px",
                  fontWeight: 700,
                  color: "var(--text-main)",
                  letterSpacing: "-0.5px",
                }}
              >
                Welcome back 👋
              </Title>
              <Text
                style={{
                  fontSize: "14px",
                  color: "var(--text-muted)",
                  marginTop: "6px",
                  display: "block",
                  lineHeight: "1.5",
                }}
              >
                Please enter your credentials to access your executive workspace.
              </Text>
            </div>

            {/* Ant Design Form */}
            <Form
              form={loginForm}
              layout="vertical"
              onFinish={onLogin}
              requiredMark={false}
              size="large"
            >
              <Form.Item
                label={
                  <Text style={{ fontWeight: 600, fontSize: "13px", color: "var(--text-main)" }}>
                    Email Address
                  </Text>
                }
                name="email"
                rules={[
                  { required: true, message: "Please enter your email address" },
                  { type: "email", message: "Please enter a valid email address" },
                ]}
                style={{ marginBottom: "20px" }}
              >
                <Input
                  prefix={<MailOutlined style={{ color: "var(--text-muted)", marginRight: "6px" }} />}
                  placeholder="name@company.com"
                  style={{
                    height: "44px",
                    borderRadius: "10px",
                    background: isDark ? "#1e293b" : "#ffffff",
                    borderColor: isDark ? "#334155" : "#e2e8f0",
                    color: "var(--text-main)",
                    fontSize: "14px",
                  }}
                />
              </Form.Item>

              <Form.Item
                label={
                  <Text style={{ fontWeight: 600, fontSize: "13px", color: "var(--text-main)" }}>
                    Password
                  </Text>
                }
                name="password"
                rules={[{ required: true, message: "Please enter your password" }]}
                style={{ marginBottom: "16px" }}
              >
                <Input.Password
                  prefix={<LockOutlined style={{ color: "var(--text-muted)", marginRight: "6px" }} />}
                  placeholder="••••••••••••"
                  style={{
                    height: "44px",
                    borderRadius: "10px",
                    background: isDark ? "#1e293b" : "#ffffff",
                    borderColor: isDark ? "#334155" : "#e2e8f0",
                    color: "var(--text-main)",
                    fontSize: "14px",
                  }}
                />
              </Form.Item>

              {/* Remember Me & Forgot Password Row */}
              <div
                style={{
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "space-between",
                  marginBottom: "28px",
                }}
              >
                <Checkbox
                  checked={rememberMe}
                  onChange={(e) => setRememberMe(e.target.checked)}
                  style={{ color: "var(--text-muted)", fontSize: "13px" }}
                >
                  Remember me
                </Checkbox>
                <a
                  href="#forgot-password"
                  onClick={(e) => {
                    e.preventDefault();
                    alert("Password resets are managed by your Security Administrator.");
                  }}
                  style={{
                    fontSize: "13px",
                    color: "#6366f1",
                    fontWeight: 600,
                    textDecoration: "none",
                  }}
                >
                  Forgot password?
                </a>
              </div>

              {/* Sign In Primary Rounded Button */}
              <Button
                htmlType="submit"
                type="primary"
                block
                loading={loginLoading}
                icon={!loginLoading && <ArrowRight size={18} />}
                style={{
                  height: "46px",
                  fontSize: "15px",
                  fontWeight: 600,
                  borderRadius: "10px",
                  background: "#4f46e5",
                  borderColor: "#4f46e5",
                  display: "flex",
                  alignItems: "center",
                  justifyContent: "center",
                  gap: "6px",
                  boxShadow: "0 4px 14px rgba(79, 70, 229, 0.25)",
                }}
              >
                Sign In
              </Button>
            </Form>

            {/* Footer Governance Tag */}
            <div
              style={{
                marginTop: "36px",
                paddingTop: "20px",
                borderTop: "1px solid var(--border-color)",
                textAlign: "center",
              }}
            >
              <Text style={{ fontSize: "12px", color: "var(--text-muted)" }}>
                Protected by Enterprise JWT Authentication & RLS Policy Matrix
              </Text>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default LoginPage;
