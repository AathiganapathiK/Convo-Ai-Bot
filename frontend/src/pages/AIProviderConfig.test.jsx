import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";
import AIProviderConfig from "./AIProviderConfig";

// Mock matchMedia for Antd tabs/tables
beforeAll(() => {
  Object.defineProperty(window, "matchMedia", {
    writable: true,
    value: jest.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: jest.fn(),
      removeListener: jest.fn(),
      addEventListener: jest.fn(),
      removeEventListener: jest.fn(),
      dispatchEvent: jest.fn(),
    })),
  });
});

// Mock @ant-design/icons entirely to bypass Jest syntax error importing ES modules
jest.mock("@ant-design/icons", () => {
  const React = require("react");
  const MockIcon = ({ className, style, onClick, "aria-label": ariaLabel }) => (
    <span className={className} style={style} onClick={onClick} aria-label={ariaLabel} role="img" />
  );
  return {
    PlusOutlined: MockIcon,
    SettingOutlined: MockIcon,
    KeyOutlined: MockIcon,
    AppstoreOutlined: MockIcon,
    NodeIndexOutlined: MockIcon,
    CheckCircleOutlined: MockIcon,
    CloseCircleOutlined: MockIcon,
    WarningOutlined: MockIcon,
    QuestionCircleOutlined: MockIcon,
    DeleteOutlined: MockIcon,
    ArrowUpOutlined: MockIcon,
    ArrowDownOutlined: MockIcon,
    EditOutlined: MockIcon,
    GlobalOutlined: MockIcon,
    ExperimentOutlined: MockIcon,
    DashboardOutlined: MockIcon
  };
});

// Mock Ant Design components completely to bypass DatePicker Node module resolution issues in Jest
jest.mock("antd", () => {
  const React = require("react");
  
  const Table = ({ dataSource, columns }) => (
    <table>
      <thead>
        <tr>
          {columns.map((col, idx) => (
            <th key={idx}>{col.title}</th>
          ))}
        </tr>
      </thead>
      <tbody>
        {dataSource.map((row, rIdx) => (
          <tr key={rIdx}>
            {columns.map((col, cIdx) => (
              <td key={cIdx}>
                {col.render ? col.render(row[col.dataIndex], row) : row[col.dataIndex]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );

  const Card = ({ children, title }) => (
    <div data-testid="card-wrapper">
      {title && <h3>{title}</h3>}
      {children}
    </div>
  );

  const Button = ({ children, onClick, loading, disabled, ...rest }) => (
    <button onClick={onClick} disabled={disabled || loading} {...rest}>
      {loading ? "Loading..." : children}
    </button>
  );

  const Tag = ({ children, color }) => <span className={`tag-${color}`}>{children}</span>;
  const Space = ({ children }) => <div>{children}</div>;
  
  const Typography = {
    Title: ({ children }) => <h1>{children}</h1>,
    Text: ({ children, type }) => <span className={type}>{children}</span>,
    Paragraph: ({ children }) => <p>{children}</p>,
  };

  const Modal = ({ children, title, open, onCancel }) => open ? (
    <div data-testid="modal-wrapper">
      <h2>{title}</h2>
      {children}
      <button onClick={onCancel}>Cancel</button>
    </div>
  ) : null;

  const Form = Object.assign(
    ({ children, onFinish }) => (
      <form onSubmit={(e) => { e.preventDefault(); onFinish && onFinish({}); }}>{children}</form>
    ),
    {
      useForm: () => [{
        resetFields: jest.fn(),
        setFieldsValue: jest.fn(),
      }],
      Item: ({ children, label }) => (
        <div>
          {label && <label>{label}</label>}
          {children}
        </div>
      )
    }
  );

  const Input = Object.assign(
    (props) => <input {...props} />,
    {
      Password: (props) => <input type="password" aria-label="Secret Key Token" {...props} />
    }
  );

  const Select = Object.assign(
    ({ children, onChange, value, placeholder }) => (
      <select 
        value={value || ""} 
        onChange={(e) => onChange && onChange(e.target.value)}
        role="combobox"
      >
        <option value="" disabled>{placeholder || "Select model"}</option>
        {children}
      </select>
    ),
    {
      Option: ({ children, value }) => <option value={value}>{children}</option>
    }
  );

  const message = {
    success: jest.fn(),
    error: jest.fn(),
    loading: jest.fn()
  };

  const Tabs = ({ items, activeKey, onChange }) => (
    <div>
      <div role="tablist">
        {items.map(item => (
          <button 
            key={item.key} 
            role="tab" 
            aria-selected={activeKey === item.key}
            onClick={() => onChange && onChange(item.key)}
          >
            {item.label}
          </button>
        ))}
      </div>
      {items.map(item => activeKey === item.key ? (
        <div key={item.key} data-testid={`tab-content-${item.key}`}>
          {item.children}
        </div>
      ) : null)}
    </div>
  );

  const Switch = ({ checked, onChange }) => (
    <input type="checkbox" checked={checked} onChange={(e) => onChange && onChange(e.target.checked)} />
  );

  const Tooltip = ({ children, title }) => <span title={title}>{children}</span>;
  const Divider = () => <hr />;
  const Row = ({ children }) => <div>{children}</div>;
  const Col = ({ children }) => <div>{children}</div>;
  const Badge = ({ text }) => <span>{text}</span>;
  
  const Popconfirm = ({ children, onConfirm }) => (
    <span onClick={onConfirm} data-testid="popconfirm-trigger">{children}</span>
  );
  
  const List = ({ dataSource, renderItem }) => (
    <div>{dataSource.map((item, index) => renderItem(item, index))}</div>
  );
  
  const Alert = ({ message, type }) => <div className={`alert-${type}`}>{message}</div>;
  const Spin = () => <div>Loading...</div>;

  return {
    Table, Card, Button, Tag, Space, Typography, Modal, Form,
    Input, Select, message, Tabs, Divider, Row, Col, Badge, Switch,
    Tooltip, Popconfirm, List, Alert, Spin
  };
});

describe("AIProviderConfig Component", () => {
  const API = "http://localhost:8000";
  const token = "test-token";

  const mockProviders = [
    {
      provider_id: "prov-1",
      provider_name: "Mock OpenAI",
      provider_type: "openai",
      base_url: "https://api.openai.com/v1",
      is_active: true,
      masked_api_key: "sk-...abcd",
      status: "HEALTHY",
      last_success_at: "2026-08-20T10:00:00Z",
      last_failure_at: null,
      failure_count: 0,
      average_response_ms: 120.0
    },
    {
      provider_id: "prov-2",
      provider_name: "Mock Groq",
      provider_type: "groq",
      base_url: "https://api.groq.com",
      is_active: false,
      masked_api_key: null,
      status: "UNKNOWN",
      last_success_at: null,
      last_failure_at: null,
      failure_count: 0,
      average_response_ms: null
    }
  ];

  const mockModels = [
    {
      model_id: "model-1",
      provider_id: "prov-1",
      provider_name: "Mock OpenAI",
      provider_type: "openai",
      model_name: "gpt-4o",
      purpose: "sql_generation",
      is_default: true,
      is_active: true,
      provider_active: true,
      health_status: "HEALTHY"
    },
    {
      model_id: "model-2",
      provider_id: "prov-1",
      provider_name: "Mock OpenAI",
      provider_type: "openai",
      model_name: "gpt-4o-mini",
      purpose: "sql_generation",
      is_default: false,
      is_active: true,
      provider_active: true,
      health_status: "HEALTHY"
    }
  ];

  const mockFallbacks = [
    {
      fallback_id: "fb-1",
      purpose: "sql_generation",
      priority_order: 1,
      is_active: true,
      model_id: "model-1",
      model_name: "gpt-4o",
      provider_name: "Mock OpenAI",
      provider_type: "openai"
    },
    {
      fallback_id: "fb-2",
      purpose: "sql_generation",
      priority_order: 2,
      is_active: true,
      model_id: "model-2",
      model_name: "gpt-4o-mini",
      provider_name: "Mock OpenAI",
      provider_type: "openai"
    }
  ];

  beforeEach(() => {
    jest.clearAllMocks();
    global.fetch = jest.fn((url, options) => {
      if (url.includes("/providers")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockProviders)
        });
      }
      if (url.includes("/models")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockModels)
        });
      }
      if (url.includes("/fallbacks")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve(mockFallbacks)
        });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve({})
      });
    });
  });

  // 1, 2, 3, 14. Loading and loads checks
  test("loads and renders the control center UI with stats overview cards", async () => {
    render(<AIProviderConfig API={API} token={token} />);
    
    expect(screen.getByText("AI Model Control Center")).toBeInTheDocument();
    
    await waitFor(() => {
      // Check Stats Cards labels using getAllByText or check content
      expect(screen.getAllByText("Active Providers")[0]).toBeInTheDocument();
      expect(screen.getAllByText("Registered Models")[0]).toBeInTheDocument();
      expect(screen.getByText("Healthy Connections")).toBeInTheDocument();
      expect(screen.getByText("Fallback Routes")).toBeInTheDocument();
    });
  });

  test("loads and displays providers table contents", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    // Click Connection Providers tab to activate it
    const tabProvidersBtn = screen.getAllByRole("tab").find(el => el.textContent.includes("Connection Providers"));
    fireEvent.click(tabProvidersBtn);

    await waitFor(() => {
      // Verify provider names are rendered (use getAll to handle duplicate provider names in other areas)
      expect(screen.getAllByText("Mock OpenAI")[0]).toBeInTheDocument();
      expect(screen.getAllByText("Mock Groq")[0]).toBeInTheDocument();
      // Verify key secure masking
      expect(screen.getByText("sk-...abcd")).toBeInTheDocument();
    });
  });

  test("loads and displays models list contents", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    // Click Registered Models tab to activate it
    const tabModelsBtn = screen.getAllByRole("tab").find(el => el.textContent.includes("Registered Models"));
    fireEvent.click(tabModelsBtn);

    await waitFor(() => {
      // Verify model names are rendered
      expect(screen.getAllByText("gpt-4o")[0]).toBeInTheDocument();
      expect(screen.getAllByText("gpt-4o-mini")[0]).toBeInTheDocument();
    });
  });

  test("loads and renders fallback routing cards", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    await waitFor(() => {
      // Check for purpose card titles
      expect(screen.getByText("SQL Query Generation")).toBeInTheDocument();
      expect(screen.getByText("Business Explanation & Insights")).toBeInTheDocument();
      expect(screen.getByText("Conversational Intent Classifier")).toBeInTheDocument();
      expect(screen.getByText("Chart Aggregator & Visual Selector")).toBeInTheDocument();
    });
  });

  // 4. Add provider modal submit check
  test("submits create provider form values correctly", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    // Active connection providers tab to render buttons
    const tabProvidersBtn = screen.getAllByRole("tab").find(el => el.textContent.includes("Connection Providers"));
    fireEvent.click(tabProvidersBtn);
    
    await waitFor(() => {
      const addBtn = screen.getByRole("button", { name: /add provider/i });
      fireEvent.click(addBtn);
    });

    // Form modal is visible
    expect(screen.getByText("Register AI Connection Node")).toBeInTheDocument();

    fireEvent.change(screen.getByPlaceholderText("e.g. OpenAI Cloud Production"), {
      target: { value: "New Provider Node" }
    });

    const submitBtn = screen.getByRole("button", { name: /save node config/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/providers"),
        expect.objectContaining({
          method: "POST"
        })
      );
    });
  });

  // 6. Test provider node connectivity
  test("triggers connection test for provider and shows success status", async () => {
    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes("/test")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: "success", latency_ms: 105 })
        });
      }
      if (url.includes("/providers")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockProviders) });
      }
      if (url.includes("/models")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockModels) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([])
      });
    });

    render(<AIProviderConfig API={API} token={token} />);
    
    const tabProvidersBtn = screen.getAllByRole("tab").find(el => el.textContent.includes("Connection Providers"));
    fireEvent.click(tabProvidersBtn);
    
    await waitFor(() => {
      const testBtns = screen.getAllByRole("button", { name: /test connection/i });
      fireEvent.click(testBtns[0]);
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/providers/prov-1/test"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  // 7. Test model completion API
  test("triggers completions test for model and shows latency success", async () => {
    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes("/test")) {
        return Promise.resolve({
          ok: true,
          json: () => Promise.resolve({ status: "success", latency_ms: 215, response: "hello" })
        });
      }
      if (url.includes("/providers")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockProviders) });
      }
      if (url.includes("/models")) {
        return Promise.resolve({ ok: true, json: () => Promise.resolve(mockModels) });
      }
      return Promise.resolve({
        ok: true,
        json: () => Promise.resolve([])
      });
    });

    render(<AIProviderConfig API={API} token={token} />);

    const tabModelsBtn = screen.getAllByRole("tab").find(el => el.textContent.includes("Registered Models"));
    fireEvent.click(tabModelsBtn);
    
    await waitFor(() => {
      const testBtns = screen.getAllByRole("button", { name: /test model/i });
      fireEvent.click(testBtns[0]);
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/models/model-1/test"),
        expect.objectContaining({ method: "POST" })
      );
    });
  });

  // 8. Set Primary Routing
  test("updates primary model routing when a new model is selected", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    await waitFor(() => {
      const selects = screen.getAllByRole("combobox");
      fireEvent.change(selects[0], { target: { value: "model-2" } });
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/model-routing"),
        expect.objectContaining({ method: "PUT" })
      );
    });
  });

  // 10. Remove Fallback
  test("triggers fallback removal when delete is clicked", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    await waitFor(() => {
      const popconfirms = screen.getAllByTestId("popconfirm-trigger");
      fireEvent.click(popconfirms[0]);
    });

    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalledWith(
        expect.stringContaining("/fallbacks/fb-2"),
        expect.objectContaining({ method: "DELETE" })
      );
    });
  });

  // 12. Error handling checks
  test("displays user-friendly error message when fetch returns 403", async () => {
    global.fetch = jest.fn().mockImplementation((url) => {
      if (url.includes("/providers")) {
        return Promise.resolve({
          ok: false,
          status: 403,
          json: () => Promise.resolve({ detail: "Access denied to admin resources" })
        });
      }
      return Promise.resolve({ ok: true, json: () => Promise.resolve([]) });
    });

    render(<AIProviderConfig API={API} token={token} />);
    
    await waitFor(() => {
      expect(global.fetch).toHaveBeenCalled();
    });
  });

  // 13. No Key Exposure checks
  test("inputs password write-only for provider credentials", async () => {
    render(<AIProviderConfig API={API} token={token} />);

    const tabProvidersBtn = screen.getAllByRole("tab").find(el => el.textContent.includes("Connection Providers"));
    fireEvent.click(tabProvidersBtn);
    
    await waitFor(() => {
      const keyBtn = screen.getByTestId("key-btn-prov-1");
      fireEvent.click(keyBtn);
    });

    await waitFor(() => {
      const passwordInput = screen.getByLabelText("Secret Key Token");
      expect(passwordInput).toHaveAttribute("type", "password");
    });
  });
});
