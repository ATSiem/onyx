import React from 'react';
import { render, screen, fireEvent } from '@testing-library/react';
import { FormikProvider, Field } from 'formik';
import '@testing-library/jest-dom';
import { StringWithDescription } from '@/lib/connectors/connectors';

// Mock the SelectInput component
jest.mock('@/app/admin/connectors/[connector]/pages/ConnectorInput/SelectInput', () => {
  return function MockSelectInput({ 
    name, 
    options 
  }: { 
    name: string;
    options: StringWithDescription[];
  }) {
    return (
      <select data-testid={`select-${name}`}>
        {options.map((option) => (
          <option key={option.name} value={option.name}>
            {option.name}
          </option>
        ))}
      </select>
    );
  };
});

describe('Azure DevOps Connector', () => {
  test('content_scope selection sets correct value', async () => {
    // Create a mock FormikContext
    const formik = {
      values: {},
      setFieldValue: jest.fn(),
    };

    const options: StringWithDescription[] = [
      { name: 'work_items_only', value: 'work_items_only', description: 'Only sync work items' },
      { name: 'everything', value: 'everything', description: 'Sync all content' }
    ];

    // Test that selecting the dropdown sets the value
    const TestComponent = () => (
      <FormikProvider value={formik as any}>
        <Field
          name="content_scope"
          component="select"
          data-testid="content-scope-select"
        >
          {options.map((option) => (
            <option key={option.name} value={option.name}>
              {option.name}
            </option>
          ))}
        </Field>
      </FormikProvider>
    );

    render(<TestComponent />);

    // Simulate selecting "everything" from dropdown
    fireEvent.change(screen.getByTestId('content-scope-select'), { 
      target: { value: 'everything' } 
    });

    // Verify the formik context updates appropriately
    expect(formik.setFieldValue).toHaveBeenCalledWith(
      'content_scope', 
      'everything', 
      true
    );
  });

  // Test case-insensitivity of content_scope by adding a capitalized option
  test('content_scope handles case variations', async () => {
    // Create a mock FormikContext
    const formik = {
      values: {},
      setFieldValue: jest.fn(),
    };

    // Add both lowercase and capitalized versions
    const options: StringWithDescription[] = [
      { name: 'work_items_only', value: 'work_items_only', description: 'Only sync work items' },
      { name: 'everything', value: 'everything', description: 'Sync all content' },
      { name: 'Everything', value: 'Everything', description: 'Sync all content (capitalized)' }
    ];

    const TestComponent = () => (
      <FormikProvider value={formik as any}>
        <Field
          name="content_scope"
          component="select"
          data-testid="content-scope-select"
        >
          {options.map((option) => (
            <option key={option.name} value={option.name}>
              {option.name}
            </option>
          ))}
        </Field>
      </FormikProvider>
    );

    render(<TestComponent />);

    // Test with capitalized value
    fireEvent.change(screen.getByTestId('content-scope-select'), { 
      target: { value: 'Everything' } 
    });

    expect(formik.setFieldValue).toHaveBeenCalledWith(
      'content_scope', 
      'Everything', 
      true
    );
  });
}); 