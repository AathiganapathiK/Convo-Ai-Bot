import React from "react";
import { Drawer, Card, Typography, Progress, List, Space } from "antd";
import { LineChartOutlined, AreaChartOutlined, BarChartOutlined, GlobalOutlined } from "@ant-design/icons";

const { Text, Paragraph } = Typography;

function ChartsDrawer({ visible, onClose }) {
  const countryRevenue = [
    { country: "United Kingdom", percentage: 82, revenue: "£6.81M", color: "#4f46e5" },
    { country: "Netherlands", percentage: 4.8, revenue: "£398K", color: "#10b981" },
    { country: "EIRE", percentage: 3.5, revenue: "£291K", color: "#f59e0b" },
    { country: "Germany", percentage: 3.2, revenue: "£265K", color: "#3b82f6" },
    { country: "France", percentage: 2.8, revenue: "£232K", color: "#ec4899" },
  ];

  const queryTypes = [
    { type: "Top Selling Items", count: 48, percentage: 34 },
    { type: "Customer Segmentation", count: 32, percentage: 22 },
    { type: "Revenue & Sales Performance", count: 45, percentage: 31 },
    { type: "Inventory & Stock Levels", count: 17, percentage: 13 },
  ];

  return (
    <Drawer
      title={<span><LineChartOutlined style={{ marginRight: 8, color: "#10b981" }} />Analytics Visualizations (Placeholders)</span>}
      placement="right"
      width={500}
      onClose={onClose}
      open={visible}
    >
      <Paragraph style={{ color: "#64748b", marginBottom: "20px" }}>
        Placeholder charts reflecting the online retail dataset contents (Revenue by Country, Query breakdown, and API activity).
      </Paragraph>

      <Space direction="vertical" style={{ width: "100%" }} size="large">
        
        {/* CARD 1: Weekly Query Activity (SVG Sparkline) */}
        <Card
          title={<span><AreaChartOutlined style={{ marginRight: 8, color: "#4f46e5" }} />Weekly AI Query Trend</span>}
          bordered
          size="small"
          style={{ borderRadius: "8px", boxShadow: "0 2px 6px rgba(0,0,0,0.02)" }}
        >
          <div style={{ padding: "10px 0" }}>
            <svg viewBox="0 0 400 120" style={{ width: "100%", height: "auto" }}>
              <defs>
                <linearGradient id="chartGradient" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#818cf8" stopOpacity="0.4" />
                  <stop offset="100%" stopColor="#818cf8" stopOpacity="0.0" />
                </linearGradient>
              </defs>
              {/* Grid Lines */}
              <line x1="0" y1="20" x2="400" y2="20" stroke="#f1f5f9" strokeWidth="1" />
              <line x1="0" y1="60" x2="400" y2="60" stroke="#f1f5f9" strokeWidth="1" />
              <line x1="0" y1="100" x2="400" y2="100" stroke="#f1f5f9" strokeWidth="1" />
              
              {/* Fill Area under chart line */}
              <path
                d="M 10 90 Q 60 40 110 70 T 210 30 T 310 80 T 390 20 L 390 110 L 10 110 Z"
                fill="url(#chartGradient)"
              />
              
              {/* Chart Line */}
              <path
                d="M 10 90 Q 60 40 110 70 T 210 30 T 310 80 T 390 20"
                fill="none"
                stroke="#4f46e5"
                strokeWidth="3"
                strokeLinecap="round"
              />
              
              {/* Dots on points */}
              <circle cx="10" cy="90" r="4" fill="#ffffff" stroke="#4f46e5" strokeWidth="2" />
              <circle cx="110" cy="70" r="4" fill="#ffffff" stroke="#4f46e5" strokeWidth="2" />
              <circle cx="210" cy="30" r="4" fill="#ffffff" stroke="#4f46e5" strokeWidth="2" />
              <circle cx="310" cy="80" r="4" fill="#ffffff" stroke="#4f46e5" strokeWidth="2" />
              <circle cx="390" cy="20" r="4" fill="#ffffff" stroke="#4f46e5" strokeWidth="2" />
              
              {/* Labels */}
              <text x="10" y="115" fontSize="10" fill="#94a3b8" textAnchor="middle">Mon</text>
              <text x="110" y="115" fontSize="10" fill="#94a3b8" textAnchor="middle">Wed</text>
              <text x="210" y="115" fontSize="10" fill="#94a3b8" textAnchor="middle">Fri</text>
              <text x="310" y="115" fontSize="10" fill="#94a3b8" textAnchor="middle">Sun</text>
              <text x="390" y="115" fontSize="10" fill="#94a3b8" textAnchor="end">Today</text>
            </svg>
          </div>
          <div style={{ display: "flex", justifyContent: "space-between", marginTop: "8px" }}>
            <Text type="secondary" style={{ fontSize: "12px" }}>Peak: 38 queries/day</Text>
            <Text type="secondary" style={{ fontSize: "12px" }}>Total weekly: 194 queries</Text>
          </div>
        </Card>

        {/* CARD 2: Revenue breakdown by Country (Mock) */}
        <Card
          title={<span><GlobalOutlined style={{ marginRight: 8, color: "#10b981" }} />Top 5 Revenue by Country</span>}
          bordered
          size="small"
          style={{ borderRadius: "8px", boxShadow: "0 2px 6px rgba(0,0,0,0.02)" }}
        >
          <List
            dataSource={countryRevenue}
            renderItem={(item) => (
              <List.Item style={{ padding: "8px 0", borderBottom: "1px solid #f1f5f9" }}>
                <div style={{ width: "100%" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "4px" }}>
                    <Text strong style={{ fontSize: "13px" }}>{item.country}</Text>
                    <Text style={{ fontSize: "13px" }}>{item.revenue} ({item.percentage}%)</Text>
                  </div>
                  <Progress percent={item.percentage} strokeColor={item.color} showInfo={false} size="small" />
                </div>
              </List.Item>
            )}
          />
        </Card>

        {/* CARD 3: Query Categories breakdown (Mock) */}
        <Card
          title={<span><BarChartOutlined style={{ marginRight: 8, color: "#f59e0b" }} />Queries by Analytical Topic</span>}
          bordered
          size="small"
          style={{ borderRadius: "8px", boxShadow: "0 2px 6px rgba(0,0,0,0.02)" }}
        >
          <List
            dataSource={queryTypes}
            renderItem={(item) => (
              <List.Item style={{ padding: "8px 0" }}>
                <div style={{ width: "100%" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "2px" }}>
                    <Text style={{ fontSize: "13px" }}>{item.type}</Text>
                    <Text strong style={{ fontSize: "13px" }}>{item.count} ({item.percentage}%)</Text>
                  </div>
                  <Progress percent={item.percentage} status="active" strokeColor="#f59e0b" showInfo={false} size="small" />
                </div>
              </List.Item>
            )}
          />
        </Card>

      </Space>
    </Drawer>
  );
}

export default ChartsDrawer;
