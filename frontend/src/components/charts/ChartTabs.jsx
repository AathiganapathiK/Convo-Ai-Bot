import React, { useState } from "react";
import { Radio, Space, Button } from "antd";
import { 
  TableOutlined, 
  BarChartOutlined, 
  LineChartOutlined, 
  PieChartOutlined,
  CloseOutlined
} from "@ant-design/icons";
import { Alert } from "antd";

import TableView from "./TableView";
import BarChartView from "./BarChartView";
import LineChartView from "./LineChartView";
import PieChartView from "./PieChartView";
import ScatterChartView from "./ScatterChartView";
const ChartTabs = ({ chart, data }) => {
  const availableViews = chart?.available_views || ["table"];
  const defaultView = chart?.recommended_view || "table";
  
  // Start with no view selected
  const [activeView, setActiveView] = useState(null);

  const renderView = () => {
    switch (activeView) {
      case "bar":
        return <BarChartView chart={chart} data={data} />;
      case "line":
        return <LineChartView chart={chart} data={data} />;
      case "pie":
        return <PieChartView chart={chart} data={data} />;
      case "table":
        return <TableView data={data} />;
      case "scatter":
        return <ScatterChartView chart={chart} data={data} />;
      default:
        return null; // Return nothing until a button is selected
    }
  };

  const getIconForView = (view) => {
    switch (view) {
      case "table": return <TableOutlined />;
      case "bar": return <BarChartOutlined />;
      case "line": return <LineChartOutlined />;
      case "pie": return <PieChartOutlined />;
      default: return null;
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px" }}>
      {chart?.analysis?.too_many_measures && (
        <Alert
          type="warning"
          showIcon
          message="Large number of measures detected. Visualization may become crowded."
          style={{ marginBottom: 12 }}
        />
      )}
      
      {chart?.analysis?.sampling_required && (
        <Alert
          type="warning"
          showIcon
          message="Large dataset detected. Sampling is recommended for optimal performance."
          style={{ marginBottom: 12 }}
        />
      )}
      {chart?.analysis?.long_labels && (
        <Alert
          type="warning"
          showIcon
          message="Long labels detected. Recommending horizontal bar chart for better readability."
          style={{ marginBottom: 12 }}
        />
      )}
      {chart?.analysis?.large_dataset && chart?.analysis?.chart_warning && (
        <Alert
          type="warning"
          showIcon
          message={chart.analysis.chart_warning}
          style={{ marginBottom: 12 }}
        />
      )}
      {chart?.analysis?.outliers_detected && (
        <Alert
          type="warning"
          showIcon
          message={
            `${chart.analysis.outlier_count} outlier(s) detected. Visualization may be skewed.`
          }
          style={{
            marginBottom: 12
          }}
        />
      )}

      <div style={{ display: "flex", justifyContent: "flex-end", alignItems: "center", gap: "12px" }}>
        {activeView && (
          <Button 
            type="text" 
            danger 
            icon={<CloseOutlined />} 
            onClick={() => setActiveView(null)}
            size="small"
          >
            Close View
          </Button>
        )}
        <Radio.Group 
          value={activeView} 
          onChange={(e) => setActiveView(e.target.value)}
          optionType="button"
          buttonStyle="solid"
          size="middle"
        >
          {availableViews.map((view) => (
            <Radio.Button key={view} value={view} style={{ textTransform: "capitalize" }}>
              <Space>
                {getIconForView(view)}
                {view}
              </Space>
            </Radio.Button>
          ))}
        </Radio.Group>
      </div>
      
      {activeView && (
        <div style={{ 
          width: "100%", 
          minHeight: "300px",
          overflowX: "auto"
        }}>
          {renderView()}
        </div>
      )}
    </div>
  

);
};

export default ChartTabs;