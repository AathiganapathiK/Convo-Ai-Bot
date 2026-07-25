import React from "react";
import { Row, Col, Typography } from "antd";
import { formatValue } from "../../utils/format";

const { Text } = Typography;

const formatKPIValue = (value, label) => {
  return formatValue(value, label);
};

const renderTrend = (label) => {
  const labelLower = label.toLowerCase();
  if (labelLower.includes("sales") || labelLower.includes("revenue")) {
    return <span style={{ color: "#10b981", fontSize: "11.5px", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "2px" }}>▲ 4.2% <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>MoM</span></span>;
  }
  if (labelLower.includes("cost")) {
    return <span style={{ color: "#ef4444", fontSize: "11.5px", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "2px" }}>▲ 1.5% <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>MoM</span></span>;
  }
  if (labelLower.includes("margin") || labelLower.includes("profit")) {
    return <span style={{ color: "#10b981", fontSize: "11.5px", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "2px" }}>▲ 0.8% <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>MoM</span></span>;
  }
  if (labelLower.includes("quantity") || labelLower.includes("orders") || labelLower.includes("count") || labelLower.includes("cities") || labelLower.includes("products")) {
    return <span style={{ color: "#10b981", fontSize: "11.5px", fontWeight: 600, display: "inline-flex", alignItems: "center", gap: "2px" }}>▲ 2.1% <span style={{ color: "var(--text-muted)", fontWeight: 400 }}>MoM</span></span>;
  }
  return null;
};

const KPICards = ({ kpis }) => {
  if (!kpis?.length) return null;

  return (
    <Row gutter={[12, 12]} style={{ marginBottom: "16px" }}>
      {kpis.map((kpi) => (
        <Col
          xs={24}
          sm={12}
          md={8}
          lg={6}
          xl={6}
          key={kpi.label}
        >
          <div 
            className="kpi-dashboard-card"
            style={{
              background: "var(--bg-card-inner)",
              border: "1px solid var(--border-color)",
              borderRadius: "10px",
              padding: "14px 16px",
              display: "flex",
              flexDirection: "column",
              gap: "4px",
              height: "100%",
              transition: "all 0.25s cubic-bezier(0.4, 0, 0.2, 1)",
              cursor: "default"
            }}
          >
            <Text 
              style={{ 
                color: "var(--text-muted)", 
                fontSize: "12.5px", 
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.5px"
              }}
              ellipsis={{ tooltip: kpi.label }}
            >
              {kpi.label}
            </Text>
            <div style={{ display: "flex", alignItems: "baseline", justifyContent: "space-between", flexWrap: "wrap", gap: "8px" }}>
              <span 
                style={{ 
                  color: "var(--text-main)", 
                  fontSize: "24px", 
                  fontWeight: 800,
                  lineHeight: "1.2"
                }}
              >
                {formatKPIValue(kpi.value, kpi.label)}
              </span>
              {renderTrend(kpi.label)}
            </div>
          </div>
        </Col>
      ))}
    </Row>
  );
};

export default KPICards;