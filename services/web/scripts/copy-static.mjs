// Copies static assets next to the compiled client code.
import { cpSync, mkdirSync } from "node:fs";

mkdirSync("dist/public", { recursive: true });
cpSync("public", "dist/public", { recursive: true });
console.log("Copied static assets to dist/public");
