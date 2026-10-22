import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setJpegQuality(95);
Config.setOverwriteOutput(true);
Config.setConcurrency(6);
// Bundled locally so renders never depend on the network.
Config.setChromiumOpenGlRenderer("swangle");
