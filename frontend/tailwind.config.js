/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx,ts,tsx}"],
  theme: {
    extend: {
      colors: {
        panel: "#ffffff",
        line: "#dfe4ee",
        ink: "#18243d",
        muted: "#667089"
      },
      boxShadow: {
        soft: "0 10px 25px rgba(21, 41, 77, 0.08)"
      }
    }
  },
  plugins: []
};
