module.exports = {
  preset: "ts-jest",
  testEnvironment: "jsdom",
  moduleNameMapper: {
    "^@/(.*)$": "<rootDir>/src/$1",
  },
  testPathIgnorePatterns: ["/node_modules/", "/tests/e2e/"],
  transform: {
    "^.+\\.(ts|tsx)$": "babel-jest"
  },
  setupFilesAfterEnv: ["<rootDir>/src/setupTests.ts"],
};
